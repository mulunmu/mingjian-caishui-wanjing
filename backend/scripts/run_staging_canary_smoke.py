"""Run a live HTTP canary smoke against the isolated staging backend."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


def _request(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: int = 60,
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


def _latest_assistant_reply(history: dict[str, Any]) -> str:
    for message in reversed(history.get("messages") or []):
        if isinstance(message, dict) and message.get("role") == "assistant":
            return str(message.get("content") or "")
    return ""


def _validate_case(
    case: dict[str, Any],
    response: dict[str, Any],
    history: dict[str, Any],
) -> dict[str, Any]:
    reply = str(response.get("reply") or "")
    canary = (response.get("data") or {}).get("canary") or {}
    canary_status = str(canary.get("status") or "")
    history_reply = _latest_assistant_reply(history)

    if not reply:
        raise AssertionError(f"{case['name']}: empty reply")
    history_match = history_reply == reply
    if case["expect_canary"] and not history_match:
        raise AssertionError(
            f"{case['name']}: history mismatch ({history_reply!r} != {reply!r})"
        )
    if case["expect_canary"]:
        if canary_status != "answered":
            raise AssertionError(
                f"{case['name']}: expected answered canary, got {canary_status!r}"
            )
        claims = (response.get("data") or {}).get("claims") or []
        if not claims:
            raise AssertionError(f"{case['name']}: answered canary returned no claims")

    return {
        "name": case["name"],
        "http_status": 200,
        "canary_status": canary_status,
        "reply_source": response.get("reply_source"),
        "reply_present": True,
        "history_match": history_match,
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
        raise SystemExit(f"demo login failed: http={code} body={login}")
    token = str(login["access_token"])

    code, enterprises = _request(
        "GET",
        f"{base}/api/v1/risk/enterprises?limit=1",
        token=token,
    )
    items = enterprises.get("items") or []
    if code != 200 or not items:
        raise SystemExit(f"enterprise lookup failed: http={code} body={enterprises}")
    subject = items[0]
    enterprise_name = subject.get("display_name") or subject["enterprise_id"]

    batch_id = time.strftime("%Y%m%d%H%M%S")
    cases = [
        {
            "name": "analysis",
            "query": f"{enterprise_name}资产负债率高不高",
            "enterprise_id": subject["enterprise_id"],
            "expect_canary": True,
        },
        {"name": "greeting", "query": "你好", "expect_canary": False},
        {"name": "capability", "query": "你能做什么？", "expect_canary": False},
        {"name": "weather", "query": "今天天气怎么样？", "expect_canary": False},
        {"name": "refusal", "query": "帮我编一个企业营收数字", "expect_canary": False},
        {"name": "abuse", "query": "他妈的这系统怎么用", "expect_canary": False},
        {
            "name": "multilingual",
            "query": "Hello, how do I generate a report?",
            "expect_canary": False,
        },
    ]

    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, 1):
        session_id = f"staging-canary-smoke-{batch_id}-{index}"
        body: dict[str, Any] = {"query": case["query"], "session_id": session_id}
        if case.get("enterprise_id"):
            body["enterprise_id"] = case["enterprise_id"]
        code, response = _request(
            "POST",
            f"{base}/api/v1/chat",
            body=body,
            token=token,
        )
        if code != 200:
            raise AssertionError(f"{case['name']}: chat http={code} body={response}")
        history_code, history = _request(
            "GET",
            f"{base}/api/v1/chat/sessions/{session_id}",
            token=token,
        )
        if history_code != 200:
            raise AssertionError(
                f"{case['name']}: history http={history_code} body={history}"
            )
        results.append(_validate_case(case, response, history))

    print(json.dumps({"batch_id": batch_id, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
