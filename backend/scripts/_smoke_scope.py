# -*- coding: utf-8 -*-
"""范围状态机审计：六类漏洞不应再出现。"""
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

    # 新会话：bootstrap → unbound
    boot = post("/api/v1/chat", {"query": "", "followup": {"type": "bootstrap", "label": "bootstrap"}}, token)
    sid = boot["session_id"]
    ds = boot.get("dialogue_state") or (boot.get("data") or {}).get("dialogue_state")
    print("BOOT scope=", ds and ds.get("scope"), "reply=", (boot.get("reply") or "")[:60])
    assert ds and ds.get("scope") == "unbound", ds
    chips = (boot.get("ui") or {}).get("chips") or (boot.get("data") or {}).get("followup_items") or []
    labels = [c.get("label") for c in chips]
    assert not any("这家能贷吗" in (x or "") for x in labels), labels
    print("PASS_#5_unbound_no_zhejia_chip")

    # #1：个体问句未绑主体 → 反问，不算 193
    ask = post("/api/v1/chat", {"query": "这家能贷吗？", "session_id": sid}, token)
    print("ASK_BIND parse=", ask.get("parse_source"), "reply=", (ask.get("reply") or "")[:80])
    assert ask.get("parse_source") == "scope_guard", ask.get("parse_source")
    assert "群体风险判断" not in (ask.get("reply") or "")
    assert "会话综合风控分析" not in (ask.get("reply") or "")
    # 反问文案可提到「全样本」，但不得给出全库结论数字/雷达
    assert "拖累因素" not in (ask.get("reply") or "")
    print("PASS_#1_no_silent_cohort")

    # 试用演示 → individual
    demo = next(
        c
        for c in ((ask.get("data") or {}).get("followup_items") or [])
        if c.get("type") == "switch_scope" and (c.get("params") or {}).get("use_demo")
    )
    sw = post(
        "/api/v1/chat",
        {"query": demo["label"], "session_id": sid, "followup": demo},
        token,
    )
    # pending_query 可能直接答能贷
    ds2 = sw.get("dialogue_state") or (sw.get("data") or {}).get("dialogue_state")
    print("AFTER_DEMO scope=", ds2 and ds2.get("scope"), "fn=", sw.get("function"), "parse=", sw.get("parse_source"))
    # 若 auto 续答，应是 enterprise；若仅切换，再问一次
    if sw.get("parse_source") == "switch_scope" or (ds2 or {}).get("scope") != "individual":
        # 再点试用无 pending
        demo2 = {
            "type": "switch_scope",
            "label": "试用演示企业",
            "target": "individual",
            "params": {"use_demo": True},
        }
        sw = post("/api/v1/chat", {"query": "试用演示企业", "session_id": sid, "followup": demo2}, token)
        ds2 = sw.get("dialogue_state") or (sw.get("data") or {}).get("dialogue_state")
    assert (ds2 or {}).get("scope") == "individual", ds2
    print("PASS_#2_demo_binds_individual")

    loan = post("/api/v1/chat", {"query": "这家能贷吗？", "session_id": sid}, token)
    print("LOAN fn=", loan.get("function"), "reply=", (loan.get("reply") or "")[:120])
    assert "193" not in (loan.get("reply") or "")
    assert "全样本" not in (loan.get("reply") or "")
    assert "会话综合风控分析" not in (loan.get("reply") or "")
    # 应像放贷场景
    assert any(k in (loan.get("reply") or "") for k in ("贷", "放贷", "附加", "谨慎", "风险")), loan.get("reply")
    print("PASS_#1#3#4_loan_individual_scenario")

    warn = post("/api/v1/chat", {"query": "哪里不对劲？", "session_id": sid}, token)
    print("WARN reply=", (warn.get("reply") or "")[:120])
    assert "会话综合风控分析" not in (warn.get("reply") or "")
    assert "全样本（193" not in (warn.get("reply") or "")
    print("PASS_#4_no_synthesis_preamble")

    # cohort 切换
    co = post(
        "/api/v1/chat",
        {
            "query": "看全库",
            "session_id": sid,
            "followup": {"type": "switch_scope", "label": "看全库", "target": "cohort"},
        },
        token,
    )
    dsc = co.get("dialogue_state") or (co.get("data") or {}).get("dialogue_state")
    assert (dsc or {}).get("scope") == "cohort", dsc
    fraud = post("/api/v1/chat", {"query": "哪里可疑要查？", "session_id": sid}, token)
    print("COHORT fraud fn=", fraud.get("function"), "flagged=", ((fraud.get("data") or {}).get("slice") or {}).get("flagged_count"))
    flagged = ((fraud.get("data") or {}).get("slice") or {}).get("flagged_count")
    assert fraud.get("function") == "fraud" or (flagged and int(flagged) > 0), (
        fraud.get("function"),
        flagged,
        (fraud.get("reply") or "")[:100],
    )
    print("PASS_cohort_fraud")

    # 在 cohort 问「这家能贷吗」应反问
    ask2 = post("/api/v1/chat", {"query": "这家能贷吗？", "session_id": sid}, token)
    assert ask2.get("parse_source") == "scope_guard", ask2.get("parse_source")
    print("PASS_#1_cohort_blocks_zhejia")

    print("ALL_SCOPE_AUDIT_OK")


if __name__ == "__main__":
    main()
