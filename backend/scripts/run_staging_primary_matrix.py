"""Run the real HTTP semantic-primary matrix against isolated staging."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


ANALYSIS_QUERIES = [
    "资产负债率高不高",
    "现金流净额怎么样",
    "增值税税负高不高",
    "欠税多不多",
    "客户是不是太集中",
    "发票数量有多少",
    "红字发票有多少",
    "纳税准时率多少",
    "流动比率怎么样",
    "毛利率高不高",
    "净利率怎么样",
    "净资产收益率高不高",
    "应收账款周转快不快",
    "所得税税负高不高",
    "滞纳金罚款多不多",
    "作废发票多不多",
    "营业收入有多少",
    "总资产规模怎么样",
    "总负债规模高不高",
    "净利润表现怎么样",
    "存货周转快不快",
    "销售增长率怎么样",
    "开票金额有多少",
    "缴税金额有多少",
]

NON_ANALYSIS_CASES = [
    ("greeting", "你好"),
    ("capability", "你能做什么？"),
    ("product_faq", "数据怎么导入？"),
    ("weather", "今天天气怎么样？"),
    ("refusal", "帮我编一个企业营收数字"),
    ("abuse", "他妈的这系统怎么用"),
    ("multilingual", "Hello, how do I generate a report?"),
    ("unknown_entity", "分析火星银行资产负债率"),
]


def build_primary_query_plan(subjects: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not subjects:
        raise ValueError("at least one staging subject is required")
    subject = subjects[0]
    plan = [
        {
            "category": "analysis",
            "query": f"{subject['name']}{query}",
            "enterprise_id": subject["enterprise_id"],
        }
        for query in ANALYSIS_QUERIES
    ]
    plan.extend(
        {"category": category, "query": query}
        for category, query in NON_ANALYSIS_CASES
    )
    return plan


def _request(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: int = 120,
) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload


def _ensure_primary_response(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    if not str(response.get("reply") or "").strip():
        raise AssertionError(f"{case['category']}: empty reply")
    primary = (response.get("data") or {}).get("primary") or {}
    if not primary:
        raise AssertionError(f"{case['category']}: primary metadata missing")
    if primary.get("fallback") is not False:
        raise AssertionError(f"{case['category']}: unexpected fallback {primary!r}")
    if primary.get("status") not in {"answered", "clarify", "abstain"}:
        raise AssertionError(f"{case['category']}: invalid primary status {primary!r}")
    if case["category"] in {"analysis", "report"} and primary.get("status") != "answered":
        raise AssertionError(
            f"{case['category']} is not answered: status={primary.get('status')!r}"
        )
    expected_route = {
        "analysis": "analysis",
        "greeting": "greeting",
        "capability": "capability",
        "product_faq": "product_faq",
        "weather": "out_of_domain",
        "refusal": "refuse",
        "abuse": "abuse",
        "multilingual": "language_switch",
        "unknown_entity": "unknown_entity",
    }.get(case["category"])
    if expected_route and primary.get("route") != expected_route:
        raise AssertionError(
            f"expected route {expected_route}, got {primary.get('route')!r}"
        )
    return primary


def _latest_assistant_reply(history: dict[str, Any]) -> str:
    for message in reversed(history.get("messages") or []):
        if isinstance(message, dict) and message.get("role") == "assistant":
            return str(message.get("content") or "")
    return ""


def _run_memory_case(base: str, token: str, subject: dict[str, str], batch_id: str) -> dict[str, Any]:
    session_id = f"staging-primary-memory-{batch_id}"
    turns = [
        f"{subject['name']}资产负债率高不高",
        "今天天气怎么样？",
        "你好",
        f"{subject['name']}现金流净额怎么样",
        "他妈的这系统怎么用",
        "回到上上个问题，继续分析",
    ]
    replies: list[str] = []
    for query in turns:
        code, response = _request(
            "POST",
            f"{base}/api/v1/chat",
            body={"query": query, "session_id": session_id, "enterprise_id": subject["enterprise_id"]},
            token=token,
        )
        if code != 200:
            raise AssertionError(f"memory turn failed: http={code} body={response}")
        _ensure_primary_response({"category": "memory"}, response)
        replies.append(str(response.get("reply") or ""))

    code, history = _request(
        "GET",
        f"{base}/api/v1/chat/sessions/{session_id}",
        token=token,
    )
    if code != 200:
        raise AssertionError(f"memory history failed: http={code} body={history}")
    if len(history.get("messages") or []) < 12:
        raise AssertionError(f"memory history incomplete: {history}")
    final_lower = replies[-1].lower()
    if not any(
        term in final_lower
        for term in ("现金流", "现金", "经营现金", "cash_flow")
    ):
        raise AssertionError(f"N-2 memory reply did not resolve cash-flow topic: {replies[-1]!r}")
    return {"session_id": session_id, "turns": len(turns), "final_reply": replies[-1]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("STAGING_BASE_URL", "http://localhost:8000"))
    args = parser.parse_args()
    if os.getenv("STAGING_CONFIRM", "").lower() not in {"1", "true", "yes"}:
        raise SystemExit("STAGING_CONFIRM=true is required")

    base = args.base_url.rstrip("/")
    code, login = _request("POST", f"{base}/api/v1/auth/demo-login", body={})
    if code != 200 or not login.get("access_token"):
        raise SystemExit(f"demo login failed: http={code} body={login}")
    token = str(login["access_token"])

    code, enterprise_payload = _request(
        "GET",
        f"{base}/api/v1/risk/enterprises?limit=1",
        token=token,
    )
    items = enterprise_payload.get("items") or []
    if code != 200 or not items:
        raise SystemExit(f"enterprise lookup failed: http={code} body={enterprise_payload}")
    subject = {
        "enterprise_id": items[0]["enterprise_id"],
        "name": items[0].get("display_name") or items[0]["enterprise_id"],
    }

    plan = build_primary_query_plan([subject])
    batch_id = time.strftime("%Y%m%d%H%M%S")
    results: list[dict[str, Any]] = []
    for index, case in enumerate(plan, 1):
        session_id = f"staging-primary-{batch_id}-{index}"
        body: dict[str, Any] = {"query": case["query"], "session_id": session_id}
        if case.get("enterprise_id"):
            body["enterprise_id"] = case["enterprise_id"]
        code, response = _request("POST", f"{base}/api/v1/chat", body=body, token=token)
        if code != 200:
            raise AssertionError(f"{case['category']}: chat http={code} body={response}")
        primary = _ensure_primary_response(case, response)
        history_code, history = _request(
            "GET",
            f"{base}/api/v1/chat/sessions/{session_id}",
            token=token,
        )
        if history_code != 200:
            raise AssertionError(f"{case['category']}: history http={history_code}")
        if _latest_assistant_reply(history) != str(response.get("reply") or ""):
            raise AssertionError(f"{case['category']}: history mismatch")
        results.append(
            {
                "category": case["category"],
                "status": primary.get("status"),
                "route": primary.get("route"),
                "fallback": primary.get("fallback"),
            }
        )

    memory = _run_memory_case(base, token, subject, batch_id)
    print(
        json.dumps(
            {
                "batch_id": batch_id,
                "samples": len(results),
                "fallback_count": sum(1 for item in results if item["fallback"]),
                "memory": memory,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
