"""Run 30 real multi-metric composition cases against isolated staging."""
from __future__ import annotations

import argparse
import itertools
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


METRIC_LABELS = [
    "资产负债率", "现金流净额", "流动比率", "毛利率",
    "净利率", "净资产收益率", "欠税", "红字发票",
]


def build_composition_query_plan(subject: dict[str, str]) -> list[dict[str, Any]]:
    pairs = list(itertools.combinations(METRIC_LABELS, 2))
    plan = [
        {
            "query": f"{subject['name']}{first}和{second}怎么样",
            "enterprise_id": subject["enterprise_id"],
        }
        for first, second in pairs
    ]
    plan.extend(
        [
            {
                "query": f"请分析{subject['name']}资产负债率，并和现金流净额一起对比",
                "enterprise_id": subject["enterprise_id"],
            },
            {
                "query": f"重点看{subject['name']}现金流净额，并解释资产负债率",
                "enterprise_id": subject["enterprise_id"],
            },
        ]
    )
    return plan[:30]


def _request(method, url, *, body=None, token=None, timeout=120):
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


def validate_composition_response(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    primary = (response.get("data") or {}).get("primary") or {}
    if primary.get("fallback") is not False:
        raise AssertionError(f"unexpected fallback: {primary!r}")
    plan_id = str(primary.get("composition_plan_id") or "")
    if not plan_id.startswith("plan-multi-metric-"):
        raise AssertionError(f"composition plan missing: {primary!r}")
    failed = primary.get("composition_failed_nodes") or []
    if failed:
        raise AssertionError(f"composition node failed: {failed!r}")
    claims = (response.get("data") or {}).get("claims") or []
    if not claims:
        raise AssertionError("composition returned no claims")
    return {
        "query": case["query"],
        "plan_id": plan_id,
        "claims": len(claims),
        "cache_hits": primary.get("composition_cache_hits") or [],
        "elapsed_ms": primary.get("composition_elapsed_ms"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("STAGING_BASE_URL", "http://localhost:8000"))
    args = parser.parse_args()
    if os.getenv("STAGING_CONFIRM", "").lower() not in {"1", "true", "yes"}:
        raise SystemExit("STAGING_CONFIRM=true is required")

    base = args.base_url.rstrip("/")
    code, login = _request("POST", f"{base}/api/v1/auth/demo-login", body={})
    if code != 200 or not login.get("access_token"):
        raise SystemExit(f"demo login failed: http={code}")
    token = str(login["access_token"])
    code, payload = _request("GET", f"{base}/api/v1/risk/enterprises?limit=1", token=token)
    items = payload.get("items") or []
    if code != 200 or not items:
        raise SystemExit(f"enterprise lookup failed: http={code}")
    subject = {
        "enterprise_id": items[0]["enterprise_id"],
        "name": items[0].get("display_name") or items[0]["enterprise_id"],
    }

    batch_id = time.strftime("%Y%m%d%H%M%S")
    results = []
    for index, case in enumerate(build_composition_query_plan(subject), 1):
        body = {
            "query": case["query"],
            "session_id": f"staging-composition-{batch_id}-{index}",
            "enterprise_id": case["enterprise_id"],
        }
        code, response = _request("POST", f"{base}/api/v1/chat", body=body, token=token)
        if code != 200:
            raise AssertionError(f"case {index}: http={code} body={response}")
        results.append(validate_composition_response(case, response))

    print(json.dumps({"batch_id": batch_id, "samples": len(results), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
