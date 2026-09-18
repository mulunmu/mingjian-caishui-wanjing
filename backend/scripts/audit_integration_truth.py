"""Audit whether stage deliverables are active in the running production path."""
from __future__ import annotations

import importlib.metadata
import json
import urllib.error
import urllib.request
from pathlib import Path

from sqlalchemy import text

from app.db.urls import get_sync_engine


BASE_URL = "http://127.0.0.1:8000/api/v1"
OUTPUT = Path("/tmp/stage22_integration_truth.json")


def request(method: str, path: str, *, token: str | None = None, body: dict | None = None):
    data = json.dumps(body or {}).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"detail": raw}
        return exc.code, payload


def db_counts() -> dict[str, int]:
    with get_sync_engine().connect() as conn:
        return {
            "validated_metrics": conn.execute(
                text("SELECT count(*) FROM metric_definition WHERE status='validated'")
            ).scalar_one(),
            "unsupported_metrics": conn.execute(
                text("SELECT count(*) FROM metric_definition WHERE status='unsupported'")
            ).scalar_one(),
            "validated_tools": conn.execute(
                text(
                    "SELECT count(*) FROM tool_definition "
                    "WHERE status='validated' AND enabled=true"
                )
            ).scalar_one(),
            "composition_blueprints": conn.execute(
                text("SELECT count(*) FROM composition_blueprint")
            ).scalar_one(),
            "composition_checkpoints": conn.execute(
                text("SELECT count(*) FROM composition_execution_checkpoint")
            ).scalar_one(),
        }


def _has_no_data_claim(payload: dict) -> bool:
    claims = (payload.get("data") or {}).get("claims") or []
    for item in claims:
        value = item.get("value") if isinstance(item, dict) else None
        if isinstance(value, dict) and value.get("metric") == "sample_count":
            try:
                if float(value.get("number") or 0) == 0:
                    return True
            except (TypeError, ValueError):
                continue
        text = str(item.get("claim") or "") if isinstance(item, dict) else ""
        if "暂无" in text and ("样本" in text or "数据" in text):
            return True
    return False


def main() -> None:
    checks: list[dict] = []

    def add(name: str, passed: bool, evidence):
        checks.append({"name": name, "passed": bool(passed), "evidence": evidence})

    status, login = request("POST", "/auth/demo-login", body={})
    token = login.get("access_token") or login.get("token")
    add("demo_login", status == 200 and bool(token), {"status": status})

    boot_status, boot = request("GET", "/chat/bootstrap", token=token)
    boot_session = boot.get("session_id")
    add(
        "bootstrap_llm_welcome",
        boot_status == 200 and boot.get("welcome_source") == "llm" and bool(boot.get("ui", {}).get("welcome")),
        {"status": boot_status, "source": boot.get("welcome_source")},
    )
    history_status, history = request(
        "GET", f"/chat/sessions/{boot_session}", token=token
    )
    history_messages = history.get("messages") if isinstance(history, dict) else None
    add(
        "bootstrap_not_in_history",
        history_status in {200, 404}
        and not (history_messages or []),
        {
            "status": history_status,
            "message_count": len(history_messages or []),
            "detail": history.get("detail") if isinstance(history, dict) else None,
        },
    )

    hello_status, hello = request(
        "POST", "/chat", token=token, body={"query": "你好"}
    )
    add(
        "non_analysis_llm_expression",
        hello_status == 200 and hello.get("reply_source") == "llm",
        {"status": hello_status, "reply_source": hello.get("reply_source")},
    )
    _, demo_scope = request(
        "POST",
        "/chat",
        token=token,
        body={
            "query": "试用演示企业",
            "followup": {
                "type": "switch_scope",
                "label": "试用演示企业",
                "target": "individual",
                "params": {"use_demo": True},
            },
        },
    )
    demo_state = demo_scope.get("dialogue_state") or {}
    add(
        "trial_demo_scope_control",
        demo_state.get("scope") == "individual"
        and demo_state.get("subject", {}).get("enterprise_id")
        and demo_scope.get("reply_source") == "llm",
        {
            "scope": demo_state.get("scope"),
            "enterprise_id": demo_state.get("subject", {}).get("enterprise_id"),
            "display_name": demo_state.get("subject", {}).get("display_name"),
        },
    )
    add(
        "langgraph_outer_active",
        hello.get("data", {}).get("primary", {}).get("orchestrator", {}).get("engine")
        == "langgraph",
        hello.get("data", {}).get("primary", {}).get("orchestrator", {}),
    )
    add(
        "process_events_emitted",
        len(hello.get("process") or []) >= 3,
        {"count": len(hello.get("process") or [])},
    )

    overview_status, overview = request(
        "POST",
        "/chat",
        token=token,
        body={"query": "企业一有哪些值得分析的点"},
    )
    primary = overview.get("data", {}).get("primary", {})
    plan_ids = primary.get("plan_tool_ids") or []
    add(
        "open_overview_dynamic_dag",
        overview_status == 200
        and primary.get("composition_strategy")
        in {"dynamic_candidate_graph", "llm_semantic_plan"}
        and len(plan_ids) >= 2,
        {
            "status": overview_status,
            "strategy": primary.get("composition_strategy"),
            "plan_tool_ids": plan_ids,
        },
    )
    claims = overview.get("data", {}).get("claims") or []
    cohort_contamination = [
        item.get("claim")
        for item in claims
        if "193" in str(item.get("claim") or "") or "全样本" in str(item.get("claim") or "")
    ]
    add(
        "individual_scope_not_contaminated",
        not cohort_contamination,
        {"contaminated_claims": cohort_contamination[:3]},
    )

    _, first_entity_turn = request(
        "POST",
        "/chat",
        token=token,
        body={"query": "企业一的税务情况"},
    )
    follow_session = first_entity_turn.get("session_id")
    _, entity_followup = request(
        "POST",
        "/chat",
        token=token,
        body={"query": "查看风险预警", "session_id": follow_session},
    )
    followup_primary = entity_followup.get("data", {}).get("primary", {})
    followup_state = entity_followup.get("dialogue_state") or {}
    add(
        "entity_context_survives_followup",
        entity_followup.get("reply") != "请补充企业名称或编号，以及想分析的具体指标。"
        and followup_state.get("scope") == "individual"
        and followup_state.get("subject", {}).get("enterprise_id"),
        {
            "reply": entity_followup.get("reply"),
            "scope": followup_state.get("scope"),
            "enterprise_id": followup_state.get("subject", {}).get("enterprise_id"),
            "route": followup_primary.get("route"),
        },
    )
    add(
        "followup_returns_chart",
        (
            isinstance(entity_followup.get("charts"), dict)
            and bool(entity_followup.get("charts", {}).get("type"))
        )
        or _has_no_data_claim(entity_followup),
        {
            "chart_type": (entity_followup.get("charts") or {}).get("type"),
            "no_data_claim": _has_no_data_claim(entity_followup),
        },
    )

    _, industry = request(
        "POST",
        "/chat",
        token=token,
        body={
            "query": "当前数据按行业是怎么划分的？有哪些行业供我们分析？",
            "session_id": follow_session,
        },
    )
    industry_primary = industry.get("data", {}).get("primary", {})
    industry_state = industry.get("dialogue_state") or {}
    industry_chart = industry.get("charts") or {}
    industry_labels = (industry_chart.get("data") or {}).get("labels") or []
    add(
        "industry_inventory_uses_real_data",
        industry_primary.get("semantic_frame", {}).get("task_type") == "distribution"
        and industry_state.get("scope") == "cohort"
        and len(industry_labels) >= 2
        and industry_chart.get("type") == "bar",
        {
            "task_type": industry_primary.get("semantic_frame", {}).get("task_type"),
            "scope": industry_state.get("scope"),
            "labels": industry_labels,
            "chart_type": industry_chart.get("type"),
        },
    )
    cohort_followups = (
        ("预警", "哪里信号最多？", "warn"),
        ("稽查", "哪里可疑要查？", "audit"),
        ("行业", "按行业拆风险等级", "rating"),
    )
    for label, query, expected_domain in cohort_followups:
        _, response = request(
            "POST",
            "/chat",
            token=token,
            body={"query": query, "session_id": follow_session},
        )
        primary = response.get("data", {}).get("primary", {})
        add(
            f"cohort_button_{label}",
        response.get("reply") != "请补充企业名称或编号，以及想分析的具体指标。"
        and (response.get("dialogue_state") or {}).get("scope") == "cohort"
        and (
            primary.get("domain") == expected_domain
            or "stratification"
            in ((primary.get("semantic_plan") or {}).get("analysis_patterns") or [])
            or primary.get("semantic_frame", {}).get("task_type") == "distribution"
        )
        and (
            label != "行业"
            or (
                ((response.get("charts") or {}).get("shape") == "categorical_distribution")
                and len((((response.get("charts") or {}).get("data") or {}).get("labels") or [])) >= 2
            )
        ),
            {
                "query": query,
                "reply": response.get("reply"),
                "domain": primary.get("domain"),
                "plan_tool_ids": primary.get("plan_tool_ids"),
                "chart_type": (response.get("charts") or {}).get("type"),
            },
        )

    versions = {}
    for package in ("langgraph", "langgraph-checkpoint-postgres", "langchain-core"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    add("langgraph_installed", bool(versions.get("langgraph")), versions)
    add(
        "langchain_not_in_core_path",
        versions.get("langchain-core") is not None,
        {
            "langchain_core": versions.get("langchain-core"),
            "note": "langchain-core is a LangGraph dependency; no separate LangChain planner is active",
        },
    )
    add(
        "finance_review_disabled_by_decision",
        __import__("os").getenv("LANGGRAPH_FINANCE_REVIEW_ENABLED") == "false",
        {"enabled": __import__("os").getenv("LANGGRAPH_FINANCE_REVIEW_ENABLED")},
    )

    counts = db_counts()
    add("metric_terminal_state", counts["unsupported_metrics"] == 36, counts)

    report = {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "database": counts,
        "versions": versions,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
