# -*- coding: utf-8 -*-
"""对话边界百场景探针：按「目标行为」验收，暴露现网全部翻车面，不先打补丁。

用法（宿主机或容器）：
  python backend/scripts/run_dialog_boundary_100.py
  python backend/scripts/run_dialog_boundary_100.py --out backend/_dialog_boundary_report.json

退出码：始终 0（探针）；报告里汇总 fail 族。统一修复后再把期望收紧为 CI。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

BASE = os.getenv("CHAT_BATCH_BASE", "http://127.0.0.1:8000")

# ── 目标行为红线（测「应该怎样」，不是「今天碰巧怎样」）──
ABSTAIN = ("暂时无法判断好坏", "请先问系统能做什么")
PREACH = ("冒充「这家」", "冒充这家", "范围选定前，我不会", "范围不清时我不会拿全样本")
OVERVIEW_MARKERS = ("行业粗览", "当前可分析样本共", "想看某一行业名单")


def _login() -> str:
    for path, body in (
        ("/api/v1/auth/login", {"email": "admin@example.com", "password": "admin123"}),
        ("/api/v1/auth/demo-login", {}),
    ):
        try:
            return post(path, body)["access_token"]
        except Exception:
            continue
    raise RuntimeError("login failed")


def post(path: str, body: dict, token: str | None = None, timeout: int = 90) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{BASE}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chat(
    token: str,
    query: str,
    *,
    session_id: str | None = None,
    followup: dict | None = None,
    enterprise_id: str | None = None,
) -> dict:
    body: dict[str, Any] = {"query": query}
    if session_id:
        body["session_id"] = session_id
    if followup:
        body["followup"] = followup
    if enterprise_id:
        body["enterprise_id"] = enterprise_id
    return post("/api/v1/chat", body, token)


# ── 场景定义：family / turns / expect ──
# expect 字段（均可选）：
#   parse_in / parse_not
#   scope
#   reply_has / reply_has_any / reply_not
#   reply_not_overview   — 不得整库复读（有行业追问时）
#   no_abstain / no_preach
#   min_len


def scenarios() -> list[dict[str, Any]]:
    S: list[dict[str, Any]] = []

    def add(sid: str, family: str, title: str, turns: list, expect: dict | None = None, **kw):
        S.append(
            {
                "id": sid,
                "family": family,
                "title": title,
                "turns": turns,
                "expect": expect or {},
                **kw,
            }
        )

    # ========== A. 范围协商 overview ==========
    for i, q in enumerate(
        [
            "我可以分析哪些企业？",
            "我能分析哪些企业",
            "库里有多少家",
            "有哪些行业",
            "怎么选企业",
            "这个系统能做什么",
            "样本有多少",
            "刚才那些家还有吗",
        ],
        1,
    ):
        add(
            f"A{i:02d}",
            "negotiate_overview",
            q,
            [{"query": q}],
            {
                "parse_in": ["negotiate_scope"],
                "reply_has_any": ["家", "行业"],
                "no_abstain": True,
                "no_preach": True,
            },
        )

    # ========== B. 行业切片 list（今日高概率整库复读 → 应 FAIL）==========
    industry_asks = [
        ("服务", "服务业的企业是那些"),
        ("服务", "服务行业有哪些企业"),
        ("服务", "服务那27家是谁"),
        ("制造", "制造业有哪些"),
        ("制造", "制造企业名单"),
        ("建筑", "建筑那些家列一下"),
        ("建筑", "建筑业有哪几家"),
        ("批发零售", "批发零售有哪些企业"),
        ("批发零售", "零售那几家是谁"),
        ("服务", "服务有多少家"),
        ("制造", "制造有多少家"),
        ("建筑", "建筑行业大概多少家"),
        ("IT软件", "IT软件有哪些企业"),
        ("服务", "刚才说的服务业再展开"),
        ("制造", "把制造那块名单给我"),
    ]
    for i, (ind, q) in enumerate(industry_asks, 1):
        add(
            f"B{i:02d}",
            "negotiate_slice",
            q,
            [
                {"query": "我能分析哪些企业？"},
                {"query": q},
            ],
            {
                "parse_in": ["negotiate_scope"],
                "reply_has_any": [ind, "家"],
                "reply_not_overview": True,  # 不得再背整库粗览范文
                "no_abstain": True,
                "no_preach": True,
            },
        )

    # ========== C. 绑主体 ==========
    bind_qs = [
        "随便来一家看看",
        "随便一家",
        "试用演示企业",
        "换一家",
        "换个企业",
        "企业3",
        "企业1",
        "建筑那家",
        "服务那家看看",
        "任意选一家给我",
    ]
    for i, q in enumerate(bind_qs, 1):
        add(
            f"C{i:02d}",
            "bind",
            q,
            [{"query": q}],
            {
                "parse_in": ["bind_subject", "switch_scope"],
                "scope": "individual",
                "no_abstain": True,
            },
        )

    # ========== D. 未绑定个体分析 → 门禁 ==========
    for i, q in enumerate(
        [
            "这家能贷吗？",
            "信用怎么样？",
            "哪里不对劲？",
            "哪里可疑要查？",
            "能放贷吗",
            "评级多少",
            "有没有异常",
            "该查谁优先",
        ],
        1,
    ):
        add(
            f"D{i:02d}",
            "scope_guard",
            q,
            [{"query": q, "fresh": True}],
            {
                "parse_in": ["scope_guard", "clarify"],
                "scope_not": "individual",  # 未绑不得静默个体
                "reply_not": ["群体风险判断", "会话综合风控"],
                "no_abstain": True,
            },
        )

    # ========== E. 绑定后个体四场景 ==========
    for i, q in enumerate(
        [
            "这家能贷吗？",
            "信用怎么样？",
            "哪里不对劲？",
            "哪里可疑要查？",
            "整体怎么样",
            "经营真实性如何",
            "和同行比怎么样",
            "要不要给额度",
            "纳税信用大概什么等级",
            "红冲要不要重点查",
            "负债压力大吗",
            "营收对得上吗",
        ],
        1,
    ):
        add(
            f"E{i:02d}",
            "analyze_individual",
            q,
            [
                {
                    "query": "试用演示",
                    "followup": {
                        "type": "switch_scope",
                        "label": "试用演示企业",
                        "target": "individual",
                        "params": {"use_demo": True},
                    },
                },
                {"query": q},
            ],
            {
                "scope": "individual",
                "reply_not": ["暂时无法判断好坏"],
                "min_len": 20,
                "no_abstain": True,
            },
        )

    # ========== F. 全库群体 ==========
    for i, q in enumerate(
        [
            "全库哪里信号最多",
            "哪里可疑要查",
            "按行业拆风险等级",
            "整体风险怎么样",
            "哪些行业最集中",
            "看全库异常",
            "193家里哪里问题大",
            "群体哪里不对劲",
            "全样本信号分布",
            "舞弊信号多吗",
        ],
        1,
    ):
        add(
            f"F{i:02d}",
            "analyze_cohort",
            q,
            [
                {
                    "query": "看全库",
                    "followup": {
                        "type": "switch_scope",
                        "label": "看全库 193 家群体",
                        "target": "cohort",
                    },
                },
                {"query": q},
            ],
            {
                "scope": "cohort",
                "no_abstain": True,
                "min_len": 15,
            },
        )

    # ========== G. FAQ 收窄 / 不得抢协商 ==========
    faq_ok = [
        ("数据怎么导入", "product_faq"),
        ("怎么导入数据", "product_faq"),
        ("报告怎么生成", "product_faq"),
        ("指标怎么算", "product_faq"),
        ("综合评分怎么算的", "product_faq"),
        ("怎么脱敏", "product_faq"),
    ]
    for i, (q, _) in enumerate(faq_ok, 1):
        add(
            f"G{i:02d}",
            "product_faq",
            q,
            [{"query": q, "fresh": True}],
            {
                "parse_in": ["product_faq"],
                "no_abstain": True,
                "reply_not_overview": True,
            },
        )
    for i, q in enumerate(
        [
            "我可以分析哪些企业？",
            "服务业有哪些",
            "随便来一家",
            "全库哪里信号最多",
            "这家能贷吗",
        ],
        1,
    ):
        add(
            f"G{i+6:02d}",
            "faq_must_not_steal",
            q,
            [{"query": q, "fresh": True}],
            {
                "parse_not": ["product_faq"],
                "no_abstain": True,
            },
        )

    # ========== H. meta / 综合 ==========
    for i, q in enumerate(
        [
            "当前在看谁",
            "现在分析的是哪家",
            "帮我综合一下",
            "会话状态怎么样",
            "我们聊到哪了",
        ],
        1,
    ):
        add(
            f"H{i:02d}",
            "meta",
            q,
            [
                {
                    "query": "demo",
                    "followup": {
                        "type": "switch_scope",
                        "target": "individual",
                        "params": {"use_demo": True},
                        "label": "试用演示企业",
                    },
                },
                {"query": q},
            ],
            {"no_abstain": True, "min_len": 8},
        )

    # ========== I. 乱答 / 低置信 ==========
    for i, q in enumerate(
        [
            "！！！哈哈哈xyz",
            "asdfghjkl",
            "今天天气怎么样",
            "帮我写首诗",
            "1234567890",
            "。。。",
        ],
        1,
    ):
        add(
            f"I{i:02d}",
            "clarify_junk",
            q,
            [{"query": q, "fresh": True}],
            {
                "parse_in": ["clarify", "negotiate_scope", "meta_session"],
                "no_abstain": True,
                # 乱答不得甩 FAQ 停机长文
                "reply_not": ["数据接入支持 Excel", "报告是本系统最大卖点"],
            },
        )

    # ========== J. chip ≡ NL ==========
    add(
        "J01",
        "chip_equiv",
        "chip negotiate",
        [
            {
                "query": "我能分析哪些企业？",
                "followup": {
                    "type": "dialog_act",
                    "label": "我能分析哪些企业？",
                    "params": {"act": "negotiate_scope", "confidence": 1.0},
                },
                "fresh": True,
            }
        ],
        {"parse_in": ["negotiate_scope"], "no_preach": True, "no_abstain": True},
    )
    add(
        "J02",
        "chip_equiv",
        "chip demo bind",
        [
            {
                "query": "试用演示企业",
                "followup": {
                    "type": "switch_scope",
                    "label": "试用演示企业",
                    "target": "individual",
                    "params": {"use_demo": True},
                },
                "fresh": True,
            }
        ],
        {"scope": "individual"},
    )
    add(
        "J03",
        "chip_equiv",
        "chip cohort",
        [
            {
                "query": "看全库 193 家群体",
                "followup": {
                    "type": "switch_scope",
                    "label": "看全库 193 家群体",
                    "target": "cohort",
                },
                "fresh": True,
            }
        ],
        {"scope": "cohort", "no_preach": True},
    )
    add(
        "J04",
        "chip_equiv",
        "NL vs chip inventory same family",
        [{"query": "我可以分析哪些企业？", "fresh": True}],
        {"parse_in": ["negotiate_scope"], "no_abstain": True},
    )

    # ========== K. 指代 / 多轮焦点 ==========
    add(
        "K01",
        "anaphora",
        "换一家后仍个体",
        [
            {
                "query": "demo",
                "followup": {
                    "type": "switch_scope",
                    "target": "individual",
                    "params": {"use_demo": True},
                    "label": "试用",
                },
            },
            {"query": "换一家"},
            {"query": "这家能贷吗"},
        ],
        {"scope": "individual", "no_abstain": True, "min_len": 15},
    )
    add(
        "K02",
        "anaphora",
        "全库后再问这家应门禁",
        [
            {
                "query": "cohort",
                "followup": {"type": "switch_scope", "target": "cohort", "label": "全库"},
            },
            {"query": "这家能贷吗"},
        ],
        {"parse_in": ["scope_guard"], "no_abstain": True},
    )
    add(
        "K03",
        "anaphora",
        "行业追问继承焦点",
        [
            {"query": "我能分析哪些企业"},
            {"query": "服务业的企业是那些"},
            {"query": "再列几个"},
        ],
        {
            "parse_in": ["negotiate_scope"],
            "reply_has_any": ["服务", "家"],
            "reply_not_overview": True,
            "no_preach": True,
        },
    )
    add(
        "K04",
        "anaphora",
        "改口建筑",
        [
            {"query": "服务业有哪些企业"},
            {"query": "那建筑呢"},
        ],
        {
            "parse_in": ["negotiate_scope"],
            "reply_has_any": ["建筑", "家"],
            "reply_not_overview": True,
        },
    )
    add(
        "K05",
        "anaphora",
        "那些还有吗",
        [
            {"query": "制造有哪些企业"},
            {"query": "那些还有吗"},
        ],
        {"parse_in": ["negotiate_scope"], "reply_not_overview": True},
    )

    # ========== L. 说教句专项 ==========
    for i, q in enumerate(
        [
            "我能分析哪些企业？",
            "看全库 193 家群体",
            "服务业的企业是那些",
            "怎么选",
        ],
        1,
    ):
        turns = [{"query": q, "fresh": True}]
        if "看全库" in q:
            turns = [
                {
                    "query": q,
                    "followup": {
                        "type": "switch_scope",
                        "target": "cohort",
                        "label": q,
                    },
                    "fresh": True,
                }
            ]
        add(
            f"L{i:02d}",
            "no_preach",
            q,
            turns,
            {"no_preach": True, "no_abstain": True},
        )

    # ========== M. 空/边界输入 ==========
    add(
        "M01",
        "edge",
        "bootstrap",
        [{"query": "", "followup": {"type": "bootstrap", "label": "bootstrap"}, "fresh": True}],
        {"parse_in": ["bootstrap"], "no_preach": True},
    )
    add(
        "M02",
        "edge",
        "超短问",
        [{"query": "贷？", "fresh": True}],
        {"no_abstain": True},
    )
    add(
        "M03",
        "edge",
        "中英混杂",
        [{"query": "service 行业有哪些 firm", "fresh": True}],
        {"parse_in": ["negotiate_scope", "clarify"], "no_abstain": True},
    )
    add(
        "M04",
        "edge",
        "错别字那些=哪些",
        [{"query": "服务业的企业是那些", "fresh": True}],
        {
            "parse_in": ["negotiate_scope"],
            "reply_not_overview": True,
            "reply_has_any": ["服务", "家"],
        },
    )

    assert len(S) >= 100, len(S)
    return S


def _check(expect: dict, resp: dict) -> list[str]:
    bad: list[str] = []
    reply = resp.get("reply") or ""
    parse = resp.get("parse_source") or ""
    ds = resp.get("dialogue_state") or (resp.get("data") or {}).get("dialogue_state") or {}
    scope = ds.get("scope")

    if expect.get("parse_in") and parse not in expect["parse_in"]:
        bad.append(f"parse={parse} want_in={expect['parse_in']}")
    if expect.get("parse_not") and parse in expect["parse_not"]:
        bad.append(f"parse_stolen={parse}")
    if expect.get("scope") and scope != expect["scope"]:
        bad.append(f"scope={scope} want={expect['scope']}")
    if expect.get("scope_not") and scope == expect["scope_not"]:
        bad.append(f"scope_forbidden={scope}")
    for s in expect.get("reply_has") or []:
        if s not in reply:
            bad.append(f"missing:{s}")
    if expect.get("reply_has_any"):
        if not any(s in reply for s in expect["reply_has_any"]):
            bad.append(f"missing_any:{expect['reply_has_any']}")
    for s in expect.get("reply_not") or []:
        if s in reply:
            bad.append(f"forbidden:{s}")
    if expect.get("reply_not_overview"):
        # 整库范文复读：切片问却吐全库 overview
        hits = sum(1 for m in OVERVIEW_MARKERS if m in reply)
        if hits >= 2 or ("193" in reply and "行业粗览" in reply and "共 193" not in reply[:20] and "「" in reply):
            # list/count 也可能提到总数；若同时行业粗览+当前可分析样本共 → 复读
            if hits >= 2:
                bad.append("overview_reread")
            elif "行业粗览" in reply and "当前可分析样本共" in reply:
                bad.append("overview_reread")
    if expect.get("no_abstain"):
        for m in ABSTAIN:
            if m in reply:
                bad.append(f"abstain:{m}")
    if expect.get("no_preach"):
        for m in PREACH:
            if m in reply:
                bad.append("preach")
                break
    if expect.get("min_len") and len(reply.strip()) < int(expect["min_len"]):
        bad.append("too_short")
    if not reply.strip() and parse not in ("bootstrap",):
        bad.append("empty")
    return bad


def run_one(token: str, sc: dict) -> dict:
    sid = None
    last = {}
    errors: list[str] = []
    turn_logs: list[dict] = []
    for t in sc["turns"]:
        if t.get("fresh"):
            sid = None
        try:
            last = chat(
                token,
                t.get("query") or "",
                session_id=sid,
                followup=t.get("followup"),
                enterprise_id=t.get("enterprise_id"),
            )
            sid = last.get("session_id") or sid
            turn_logs.append(
                {
                    "query": t.get("query"),
                    "parse": last.get("parse_source"),
                    "scope": (last.get("dialogue_state") or {}).get("scope"),
                    "reply_head": (last.get("reply") or "")[:120],
                }
            )
        except urllib.error.HTTPError as e:
            errors.append(f"HTTP {e.code}")
            turn_logs.append({"query": t.get("query"), "error": e.code})
            return {
                "id": sc["id"],
                "family": sc["family"],
                "title": sc["title"],
                "ok": False,
                "errors": errors,
                "turns": turn_logs,
            }
        except Exception as e:
            errors.append(str(e)[:80])
            return {
                "id": sc["id"],
                "family": sc["family"],
                "title": sc["title"],
                "ok": False,
                "errors": errors,
                "turns": turn_logs,
            }

    # 只验最后一轮（多轮场景的期望落在追问上）
    bad = _check(sc.get("expect") or {}, last)
    return {
        "id": sc["id"],
        "family": sc["family"],
        "title": sc["title"],
        "ok": not bad,
        "errors": bad,
        "turns": turn_logs,
        "final_parse": last.get("parse_source"),
        "final_scope": (last.get("dialogue_state") or {}).get("scope"),
        "final_reply": (last.get("reply") or "")[:240],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_dialog_boundary_report.json")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（调试）")
    args = ap.parse_args()

    all_sc = scenarios()
    if args.limit:
        all_sc = all_sc[: args.limit]
    print(f"SCENARIOS={len(all_sc)} BASE={BASE}")
    token = _login()
    results = []
    t0 = time.time()
    for i, sc in enumerate(all_sc, 1):
        r = run_one(token, sc)
        results.append(r)
        mark = "OK  " if r["ok"] else "FAIL"
        err = ",".join(r["errors"][:3]) if r["errors"] else ""
        print(f"{mark} [{r['id']}] {r['family']} :: {r['title'][:40]} :: {err}")

    by_fam: dict[str, dict[str, int]] = {}
    fail_samples: dict[str, list] = {}
    for r in results:
        fam = r["family"]
        by_fam.setdefault(fam, {"ok": 0, "fail": 0})
        if r["ok"]:
            by_fam[fam]["ok"] += 1
        else:
            by_fam[fam]["fail"] += 1
            fail_samples.setdefault(fam, []).append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "errors": r["errors"],
                    "reply": r.get("final_reply"),
                    "parse": r.get("final_parse"),
                }
            )

    ok_n = sum(1 for r in results if r["ok"])
    fail_n = len(results) - ok_n
    report = {
        "total": len(results),
        "ok": ok_n,
        "fail": fail_n,
        "elapsed_sec": round(time.time() - t0, 1),
        "by_family": by_fam,
        "fail_samples": fail_samples,
        "results": results,
        "root_cause_hints": [
            "negotiate_slice / anaphora 大量 overview_reread → 库存无 ask_kind/filters/focus",
            "no_preach 失败 → 说教句写死在 inventory/welcome",
            "bind/analyze 失败 → DialogAct 槽位或门禁顺序问题",
            "faq_must_not_steal 失败 → FAQ 仍抢答",
            "clarify_junk 失败 → 乱答落入错误 act 或空答复",
        ],
    }
    out = args.out
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n======== SUMMARY ========")
    print(f"total={len(results)} ok={ok_n} fail={fail_n}")
    for fam, st in sorted(by_fam.items(), key=lambda x: -x[1]["fail"]):
        print(f"  {fam}: ok={st['ok']} fail={st['fail']}")
    print(f"report → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
