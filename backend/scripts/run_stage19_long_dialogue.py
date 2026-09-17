"""Stage 19: four 40-turn long conversations with content-level topic recall."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

BASE_URL = "http://127.0.0.1:8000"


def _request(method: str, path: str, *, body: dict | None = None, token: str | None = None) -> tuple[int, dict, float]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8")), (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload, (time.perf_counter() - started) * 1000


def _login() -> str:
    code, payload, _ = _request("POST", "/api/v1/auth/demo-login", body={})
    if code != 200 or not payload.get("access_token"):
        raise RuntimeError(f"demo login failed: {code} {payload}")
    return str(payload["access_token"])


def _subject(token: str) -> dict[str, str]:
    code, payload, _ = _request("GET", "/api/v1/risk/enterprises?limit=1", token=token)
    items = payload.get("items") or []
    if code != 200 or not items:
        raise RuntimeError(f"enterprise lookup failed: {code} {payload}")
    return {
        "enterprise_id": str(items[0]["enterprise_id"]),
        "name": str(items[0].get("display_name") or items[0]["enterprise_id"]),
    }


def _scenario(
    name: str,
    first: str,
    middle: list[str],
    final: str,
    expected: tuple[str, ...],
    subject: dict[str, str],
    token: str,
) -> dict:
    session_id = f"stage19-{name}-{uuid.uuid4().hex[:8]}"
    queries = [first] + middle + [final]
    replies: list[str] = []
    errors: list[str] = []
    for index, query in enumerate(queries, 1):
        body = {"query": query, "session_id": session_id, "enterprise_id": subject["enterprise_id"]}
        code, payload, _ = _request("POST", "/api/v1/chat", body=body, token=token)
        if code != 200:
            errors.append(f"turn_{index}_http={code}")
            continue
        reply = str(payload.get("reply") or "")
        replies.append(reply)
        primary = (payload.get("data") or {}).get("primary") or {}
        if primary.get("fallback") is not False:
            errors.append(f"turn_{index}_fallback")
    final_reply = replies[-1] if replies else ""
    if not any(term.lower() in final_reply.lower() for term in expected):
        errors.append(f"topic_not_recalled:{expected}")
    return {"name": name, "turns": len(queries), "final_reply": final_reply, "ok": not errors, "errors": errors}


def run() -> dict:
    token = _login()
    subject = _subject(token)
    scenarios = [
        (
            "tax-correction",
            f"{subject['name']}增值税税负高不高",
            ["你好"] * 38,
            "不对，我说的是税负的事，继续分析",
            ("税",),
        ),
        (
            "cash-backref",
            f"{subject['name']}现金流净额怎么样",
            ["你好"] * 38,
            "前面那个现金流的问题再展开",
            ("现金流", "现金"),
        ),
        (
            "n2-rollback",
            "你好",
            ["你好"] * 36 + [f"{subject['name']}资产负债率高不高", "你好"],
            "回到上上个问题继续分析",
            ("资产", "负债", "欠债"),
        ),
        (
            "semantic-content",
            f"{subject['name']}客户数量有多少",
            ["你好"] * 38,
            "之前聊的客户数量那个再展开",
            ("客户",),
        ),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda item: _scenario(*item, subject, token), scenarios))
    failures = [item for item in results if not item["ok"]]
    return {"total": len(results), "passed": len(results) - len(failures), "failed": len(failures), "failures": failures, "results": results}


def main() -> None:
    global BASE_URL
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    BASE_URL = args.base_url.rstrip("/")
    report = run()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"stage19 passed={report['passed']}/{report['total']} failed={report['failed']}")
    raise SystemExit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
