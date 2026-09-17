"""Small dependency-free HTTP helpers for evaluation scripts."""
from __future__ import annotations

import json
from urllib import request


def post_json(url: str, payload: dict, *, token: str | None = None, timeout: int = 90) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def login(base_url: str, email: str, password: str) -> str:
    result = post_json(
        f"{base_url.rstrip('/')}/api/v1/auth/login",
        {"email": email, "password": password},
    )
    return str(result["access_token"])
