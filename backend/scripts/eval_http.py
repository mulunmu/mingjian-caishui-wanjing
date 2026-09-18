"""Small dependency-free HTTP helpers for evaluation scripts."""
from __future__ import annotations

import json
import time
from urllib import request
from urllib.error import HTTPError


def post_json(url: str, payload: dict, *, token: str | None = None, timeout: int = 90) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, headers=headers, method="POST")
    for attempt in range(5):
        try:
            with request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            return json.loads(raw)
        except HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
            time.sleep(min(max(delay, 0.05), 2.0))
    raise RuntimeError("unreachable evaluation request state")


def login(base_url: str, email: str, password: str) -> str:
    result = post_json(
        f"{base_url.rstrip('/')}/api/v1/auth/login",
        {"email": email, "password": password},
    )
    return str(result["access_token"])
