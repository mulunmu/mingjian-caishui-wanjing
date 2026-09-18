"""Real HTTP audit for the routing cases that previously crossed contexts."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any


def _request(method: str, url: str, *, body=None, token=None, timeout=120):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {"detail": exc.read().decode("utf-8", errors="replace")}


def _turn(base: str, token: str, session_id: str, query: str, followup=None):
    body = {"query": query, "session_id": session_id}
    if followup:
        body["followup"] = followup
    return _request("POST", f"{base}/api/v1/chat", body=body, token=token)


def _scope_cohort(base: str, token: str, session_id: str) -> None:
    code, payload = _turn(
        base,
        token,
        session_id,
        "看全库 193 家群体",
        {"type": "switch_scope", "label": "看全库 193 家群体", "target": "cohort"},
    )
    if code != 200:
        raise AssertionError(f"cohort switch failed: {code} {payload}")


def _assert_case(case: str, response: dict[str, Any], *, route="analysis", focus_must=None, changed_from=None):
    primary = (response.get("data") or {}).get("primary") or {}
    frame = primary.get("semantic_frame") or {}
    if primary.get("route") != route:
        raise AssertionError(f"{case}: route={primary.get('route')} expected={route}")
    focus = primary.get("analysis_focus") or (response.get("data") or {}).get("analysis_focus") or {}
    values = focus.get("industry_l1_values") or ([focus.get("industry_l1")] if focus.get("industry_l1") else [])
    if focus_must and focus_must not in values:
        raise AssertionError(f"{case}: focus={values} missing={focus_must}")
    if changed_from and changed_from in values:
        raise AssertionError(f"{case}: stale focus {values}")
    claims = (response.get("data") or {}).get("claims") or []
    comparison_claims = [
        item for item in claims
        if str(((item.get("value") or {}).get("metric") or "")).startswith("compare_")
    ]
    return {
        "case": case,
        "route": primary.get("route"),
        "task_type": frame.get("task_type"),
        "analysis_pattern": frame.get("analysis_pattern"),
        "focus": values,
        "plan_id": primary.get("composition_plan_id"),
        "comparison_claim_count": len(comparison_claims),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    code, login = _request("POST", f"{base}/api/v1/auth/demo-login", body={})
    if code != 200 or not login.get("access_token"):
        raise SystemExit(f"demo login failed: {code}")
    token = str(login["access_token"])
    batch = time.strftime("%Y%m%d%H%M%S")
    rows: list[dict[str, Any]] = []

    session = f"intent-audit-{batch}-1"
    _scope_cohort(base, token, session)
    code, payload = _turn(base, token, session, "制造业的行业地位")
    if code != 200:
        raise AssertionError(payload)
    rows.append(_assert_case("industry_status", payload, focus_must="制造"))

    session = f"intent-audit-{batch}-2"
    _scope_cohort(base, token, session)
    code, payload = _turn(base, token, session, "批发零售的税票舞弊情况")
    if code != 200:
        raise AssertionError(payload)
    rows.append(_assert_case("industry_invoice_fraud", payload, focus_must="批发零售"))

    session = f"intent-audit-{batch}-3"
    _scope_cohort(base, token, session)
    code, payload = _turn(base, token, session, "制造业和软件的经营真实性对比")
    if code != 200:
        raise AssertionError(payload)
    row = _assert_case("multi_industry_compare", payload, focus_must="制造")
    if "IT软件" not in row["focus"]:
        raise AssertionError(f"multi_industry_compare missing IT软件: {row}")
    if int(row["comparison_claim_count"]) <= 0:
        raise AssertionError(f"multi_industry_compare has no deterministic comparison claims: {row}")
    rows.append(row)

    session = f"intent-audit-{batch}-4"
    _scope_cohort(base, token, session)
    code, payload = _turn(base, token, session, "制造业的税负结构")
    if code != 200:
        raise AssertionError(payload)
    rows.append(_assert_case("industry_focus_first", payload, focus_must="制造"))
    code, payload = _turn(base, token, session, "那它的税负呢")
    if code != 200:
        raise AssertionError(payload)
    rows.append(_assert_case("industry_sticky_followup", payload, focus_must="制造"))
    code, payload = _turn(base, token, session, "软件行业呢")
    if code != 200:
        raise AssertionError(payload)
    rows.append(_assert_case("industry_explicit_switch", payload, focus_must="IT软件", changed_from="制造"))

    session = f"intent-audit-{batch}-5"
    _scope_cohort(base, token, session)
    _turn(base, token, session, "重新选范围", {"type": "switch_scope", "label": "重新选范围", "target": "unbound"})
    code, payload = _turn(base, token, session, "制造业的行业地位")
    if code != 200:
        raise AssertionError(payload)
    rows.append(_assert_case("industry_after_reset", payload, focus_must="制造"))

    session = f"intent-audit-{batch}-6"
    _scope_cohort(base, token, session)
    code, payload = _turn(base, token, session, "有哪些行业")
    if code != 200:
        raise AssertionError(payload)
    rows.append(_assert_case("industry_inventory", payload, route="inventory"))

    print(json.dumps({"passed": True, "batch_id": batch, "cases": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
