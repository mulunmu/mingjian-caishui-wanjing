# -*- coding: utf-8 -*-
"""DialogAct HTTP 验收：三触发 + 负例 + 乱答。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"
ABSTAIN = ("暂时无法判断好坏", "请先问系统能做什么")


def post(path, body, token=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{BASE}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def assert_inventory(resp, label):
    reply = resp.get("reply") or ""
    print(f"[{label}] parse={resp.get('parse_source')} reply={reply[:100]}")
    assert resp.get("parse_source") == "negotiate_scope", resp.get("parse_source")
    assert "193" in reply or "家" in reply, reply
    for m in ABSTAIN:
        assert m not in reply, m


def main():
    token = post("/api/v1/auth/login", {"email": "admin@example.com", "password": "admin123"})[
        "access_token"
    ]
    boot = post(
        "/api/v1/chat",
        {"query": "", "followup": {"type": "bootstrap", "label": "bootstrap"}},
        token,
    )
    sid = boot["session_id"]

    # 负例 NL
    neg = post("/api/v1/chat", {"query": "我可以分析哪些企业？", "session_id": sid}, token)
    assert_inventory(neg, "NL_inventory")

    # chip dialog_act
    chip = post(
        "/api/v1/chat",
        {
            "session_id": sid,
            "query": "我能分析哪些企业？",
            "followup": {
                "type": "dialog_act",
                "label": "我能分析哪些企业？",
                "params": {"act": "negotiate_scope", "confidence": 1.0},
            },
        },
        token,
    )
    assert_inventory(chip, "CHIP_inventory")

    # chip 看全库
    cohort_chip = post(
        "/api/v1/chat",
        {
            "session_id": sid,
            "query": "看全库 193 家群体",
            "followup": {"type": "switch_scope", "label": "看全库 193 家群体", "target": "cohort"},
        },
        token,
    )
    assert_inventory(cohort_chip, "CHIP_cohort_inventory")
    ds = cohort_chip.get("dialogue_state") or {}
    assert ds.get("scope") == "cohort", ds

    # 指代
    ana = post("/api/v1/chat", {"query": "刚才那些家还有吗", "session_id": sid}, token)
    assert_inventory(ana, "ANAPHORA_inventory")

    # 绑主体 NL
    bind = post("/api/v1/chat", {"query": "随便来一家看看", "session_id": None}, token)
    print("[bind]", bind.get("parse_source"), bind.get("dialogue_state"))
    assert (bind.get("dialogue_state") or {}).get("scope") == "individual"

    # 换一家
    sid2 = bind["session_id"]
    swap = post("/api/v1/chat", {"query": "换一家", "session_id": sid2}, token)
    print("[swap]", swap.get("parse_source"), swap.get("dialogue_state"))
    assert (swap.get("dialogue_state") or {}).get("scope") == "individual"

    # 群体分析 NL
    g = post(
        "/api/v1/chat",
        {
            "session_id": None,
            "query": "全库哪里信号最多",
            "followup": {
                "type": "dialog_act",
                "label": "全库哪里信号最多",
                "params": {
                    "act": "analyze",
                    "scenario": "warn",
                    "scope_target": "cohort",
                    "confidence": 1.0,
                },
            },
        },
        token,
    )
    print("[cohort_analyze]", g.get("parse_source"), (g.get("reply") or "")[:120])
    for m in ABSTAIN:
        assert m not in (g.get("reply") or ""), m

    # 乱答
    junk = post("/api/v1/chat", {"query": "！！！哈哈哈xyz乱讲", "session_id": None}, token)
    print("[junk]", junk.get("parse_source"), (junk.get("reply") or "")[:80])
    assert junk.get("parse_source") == "clarify"

    # 个体门禁仍在
    ask = post("/api/v1/chat", {"query": "这家能贷吗？", "session_id": None}, token)
    print("[ask_bind]", ask.get("parse_source"), (ask.get("reply") or "")[:80])
    assert ask.get("parse_source") == "scope_guard"

    print("ALL_HTTP_DIALOG_ACT_OK")


if __name__ == "__main__":
    main()
