# -*- coding: utf-8 -*-
import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(path, body, token=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{BASE}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    login = post("/api/v1/auth/login", {"email": "admin@example.com", "password": "admin123"})
    token = login["access_token"]
    print("LOGIN_OK")

    faq = post("/api/v1/chat", {"query": "这个系统能做什么"}, token)
    items = (faq.get("data") or {}).get("followup_items") or []
    labels = [x.get("label") for x in items]
    print("FAQ", labels, [x.get("type") for x in items])
    assert not any(
        x in (labels or []) for x in ["这个系统能做什么", "数据怎么导入", "报告怎么生成"]
    ), labels
    print("PASS_FAQ_NO_LOOP")

    fraud = post(
        "/api/v1/chat",
        {"query": "哪里可疑要查？", "session_id": faq.get("session_id")},
        token,
    )
    print(
        "FRAUD fn=",
        fraud.get("function"),
        "flagged=",
        ((fraud.get("data") or {}).get("slice") or {}).get("flagged_count"),
    )
    fitems = (fraud.get("data") or {}).get("followup_items") or []
    for x in fitems:
        print(" ", x.get("type"), x.get("op"), x.get("target"), x.get("label"))
    dd = next(
        (
            x
            for x in fitems
            if x.get("type") == "drilldown" and x.get("op") == "group_by_industry"
        ),
        None,
    )
    assert dd, fitems
    print("PASS_HAS_DRILLDOWN")

    drill = post(
        "/api/v1/chat",
        {"query": dd["label"], "session_id": fraud.get("session_id"), "followup": dd},
        token,
    )
    print(
        "DRILL parse=",
        drill.get("parse_source"),
        "chart=",
        (drill.get("charts") or {}).get("type"),
    )
    print("DRILL reply=", (drill.get("reply") or "")[:200])
    assert drill.get("parse_source") == "drilldown"
    print("PASS_DRILLDOWN")

    act = next(x for x in fitems if x.get("type") == "action")
    action = post(
        "/api/v1/chat",
        {
            "query": act["label"],
            "session_id": fraud.get("session_id"),
            "followup": act,
        },
        token,
    )
    print(
        "ACTION parse=",
        action.get("parse_source"),
        "reply=",
        (action.get("reply") or "")[:160],
    )
    assert action.get("parse_source") == "action"
    print("PASS_ACTION")

    blob = "".join(
        (x.get("label") or "")
        for x in items
        + fitems
        + ((drill.get("data") or {}).get("followup_items") or [])
    )
    assert "附录" not in blob
    print("PASS_NO_APPENDIX")

    req = urllib.request.Request(f"{BASE}/api/v1/risk/enterprises?limit=12")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        ents = json.loads(r.read().decode())
    print("ENTS", len(ents.get("items") or []), "/", ents.get("total"))
    assert len(ents.get("items") or []) <= 12
    print("PASS_LIMIT")
    print("ALL_SMOKE_OK")


if __name__ == "__main__":
    main()
