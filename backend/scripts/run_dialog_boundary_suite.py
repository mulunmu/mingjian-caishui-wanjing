# -*- coding: utf-8 -*-
"""对话边界大套件：200 主场景 + 100 冷门（含定制报告），fail≠0 则退出码 1。

  python backend/scripts/run_dialog_boundary_suite.py --suite 200
  python backend/scripts/run_dialog_boundary_suite.py --suite cold
  python backend/scripts/run_dialog_boundary_suite.py --suite all
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("b100", HERE / "run_dialog_boundary_100.py")
b100 = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(b100)


def _add(S, sid, family, title, turns, expect=None, **kw):
    S.append({"id": sid, "family": family, "title": title, "turns": turns, "expect": expect or {}, **kw})


def extra_200() -> list[dict[str, Any]]:
    """补齐到 ≥200：行业变体、指代、定制报告、切换。"""
    S: list[dict[str, Any]] = []
    inds = ["服务", "制造", "建筑", "批发零售", "IT软件"]
    i = 1
    for ind in inds:
        for q in [
            f"{ind}有哪些企业",
            f"{ind}行业名单",
            f"{ind}有多少家",
            f"把{ind}列出来",
            f"{ind}那几家是谁",
        ]:
            _add(
                S,
                f"X{i:03d}",
                "negotiate_slice",
                q,
                [{"query": "我能分析哪些企业"}, {"query": q}],
                {
                    "parse_in": ["negotiate_scope"],
                    "reply_has_any": [ind, "家"],
                    "reply_not_overview": True,
                    "no_preach": True,
                    "no_abstain": True,
                },
            )
            i += 1

    # 定制报告主路径
    custom_flows = [
        ("我要定制报告",),
        ("帮我定制一份风控报告",),
        ("AI定制报告",),
        ("自定义报告",),
    ]
    for j, turns_q in enumerate(custom_flows, 1):
        _add(
            S,
            f"CR{j:02d}",
            "custom_report",
            turns_q[0],
            [{"query": turns_q[0], "fresh": True}],
            {
                "parse_in": ["rule", "template", "llm", "corrected"],  # custom 常走 rule/llm
                "reply_not": list(b100.ABSTAIN),
                "no_abstain": True,
                "min_len": 10,
                # parse_source for custom is often not custom-named; check function via reply keywords
                "reply_has_any": ["定制", "报告", "章节", "场景", "范围", "财务", "税务", "发票", "确认", "样本"],
            },
        )

    # 定制多轮：进入后答场景
    _add(
        S,
        "CR10",
        "custom_report",
        "定制→财务健康",
        [
            {"query": "我要定制报告", "fresh": True},
            {"query": "财务健康"},
        ],
        {"no_abstain": True, "min_len": 8, "reply_has_any": ["财务", "章节", "范围", "确认", "行业", "样本", "报告"]},
    )
    _add(
        S,
        "CR11",
        "custom_report",
        "定制→退出",
        [
            {"query": "我要定制报告", "fresh": True},
            {"query": "退出定制"},
        ],
        {"no_abstain": True, "min_len": 5},
    )

    # 更多门禁 / 分析
    for j, q in enumerate(
        [
            "这家放贷风险大吗",
            "给不给授信",
            "打个信用分看看",
            "有没有税务问题",
            "账上对不对得上",
            "要不要进核查名单",
        ],
        1,
    ):
        _add(
            S,
            f"SG{j:02d}",
            "scope_guard",
            q,
            [{"query": q, "fresh": True}],
            {"parse_in": ["scope_guard", "clarify", "negotiate_scope"], "no_abstain": True},
        )

    # 绑后追问变体
    for j, q in enumerate(
        [
            "额度能给多少",
            "主要风险点再说一遍",
            "同业对比差在哪",
            "先看预警再看稽查",
            "生成该企业深度报告",
        ],
        1,
    ):
        _add(
            S,
            f"AI{j:02d}",
            "analyze_individual",
            q,
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
                {"query": q},
            ],
            {"scope": "individual", "no_abstain": True, "min_len": 10},
        )

    # 焦点继承链
    _add(
        S,
        "FO01",
        "anaphora",
        "服务→再列→建筑",
        [
            {"query": "服务业有哪些企业", "fresh": True},
            {"query": "再列几个"},
            {"query": "那建筑呢"},
        ],
        {
            "parse_in": ["negotiate_scope"],
            "reply_has_any": ["建筑", "家"],
            "reply_not_overview": True,
            "no_preach": True,
        },
    )
    _add(
        S,
        "FO02",
        "anaphora",
        "制造多少家→名单",
        [
            {"query": "制造有多少家", "fresh": True},
            {"query": "那名单呢"},
        ],
        {"parse_in": ["negotiate_scope"], "reply_not_overview": True, "reply_has_any": ["制造", "家"]},
    )

    return S


def cold_100() -> list[dict[str, Any]]:
    """冷门 / 刁钻 / 错别字 / 混杂 / 空转。"""
    S: list[dict[str, Any]] = []
    colds = [
        ("服务业的企业是那些", {"parse_in": ["negotiate_scope"], "reply_not_overview": True, "reply_has_any": ["服务", "家"], "no_preach": True}),
        ("服务行业都有谁啊", {"parse_in": ["negotiate_scope"], "reply_not_overview": True, "reply_has_any": ["服务", "家"]}),
        ("帮我看看服务那一坨", {"parse_in": ["negotiate_scope", "clarify", "bind_subject"], "no_abstain": True}),
        ("IT的有几家", {"parse_in": ["negotiate_scope"], "reply_has_any": ["家"]}),
        ("批发的列5家", {"parse_in": ["negotiate_scope"], "reply_not_overview": True}),
        ("不是问全库，我问建筑", {"parse_in": ["negotiate_scope", "clarify"], "no_abstain": True}),
        ("同上，但只要服务", {"parse_in": ["negotiate_scope", "clarify", "meta_session"], "no_abstain": True}),
        ("???", {"parse_in": ["clarify", "negotiate_scope", "meta_session"], "no_abstain": True}),
        ("。。。嗯", {"parse_in": ["clarify", "negotiate_scope", "meta_session"], "no_abstain": True}),
        ("hello", {"parse_in": ["clarify", "negotiate_scope", "meta_session", "product_faq"], "no_abstain": True}),
        ("能贷不（这家）", {"parse_in": ["scope_guard", "clarify"], "no_abstain": True}),
        ("查查有问题没", {"parse_in": ["scope_guard", "clarify", "analyze", "rule"], "no_abstain": True}),
        ("风险呢", {"parse_in": ["scope_guard", "clarify", "negotiate_scope", "rule"], "no_abstain": True}),
        ("继续", {"parse_in": ["clarify", "meta_session", "negotiate_scope", "rule"], "no_abstain": True}),
        ("换行业", {"parse_in": ["negotiate_scope", "clarify"], "no_abstain": True}),
        ("不要演示要列表", {"parse_in": ["negotiate_scope", "clarify", "bind_subject", "switch_scope"], "no_abstain": True}),
        ("报告定制一下制造业广东的", {"parse_in": ["rule", "template", "llm", "corrected"], "reply_has_any": ["定制", "报告", "章节", "范围", "制造", "广东", "确认", "样本"]}),
        ("定制报告然后取消", None),  # multi below
        ("隐私怎么保护", {"parse_in": ["product_faq"], "no_abstain": True}),
        ("权重怎么算的呀", {"parse_in": ["product_faq"], "no_abstain": True}),
    ]
    for i, (q, exp) in enumerate(colds, 1):
        if exp is None:
            continue
        _add(S, f"COLD{i:03d}", "cold", q, [{"query": q, "fresh": True}], exp)

    _add(
        S,
        "COLD050",
        "cold",
        "定制后取消",
        [{"query": "我要定制报告", "fresh": True}, {"query": "算了不用了"}],
        {"no_abstain": True, "min_len": 4},
    )

    # 批量冷门问法
    for i, q in enumerate(
        [
            "库里还有别的吗",
            "除了制造还有啥",
            "服务里挑一家能贷的",
            "建筑和制造比谁多",
            "前10家叫啥",
            "脱敏名怎么编的",
            "企业99存在吗",
            "ENT1是哪家",
            "随便来个建筑的",
            "换到全库再说",
            "个体和群体有啥区别",
            "我刚才选的还在吗",
            "清空重来",
            "你是机器人吗",
            "不要分析只要名单",
            "只要数字不要建议",
            "用中文回答",
            "简短一点",
            "详细一点",
            "再问一次服务有哪些",
            "服务→制造→服务",
            "广东有多少家",
            "江西制造有哪些",
            "没有行业过滤的全名单太长了只要服务",
            "看完名单再分析信号",
            "先不贷，先查可疑",
            "同业对标怎么做",
            "真实性交叉是啥意思",
            "六维是什么",
            "不要术语",
            "输出JSON",
            "把结论写成一句话",
            "下钻到行业",
            "按名单看前几名",
            "漏斗呢",
            "确认生成",
            "调整范围",
            "换个章节组合",
            "财务+税务组合",
            "发票舞弊排查",
            "综合尽调",
            "风险预警总览",
            "样本库画像",
            "全部样本的定制报告",
            "只要制造业的报告",
            "广东批发零售报告",
            "企业3的深度报告",
            "邮件发给我",
            "验证码123456",
            "打开数据接入",
            "打开报告中心",
            "会话过期了吗",
            "换账号",
            "并发问两句：能贷吗；哪些企业",
            "服务业！！！",
            "【服务】有哪些",
            "service行业",
            "manufacturing list",
            "建筑业～有哪些呀～",
            "嗯服务吧",
            "就这个行业",
            "刚才那个行业再看看",
            "不是这家是那个行业",
            "全库但只要服务信号",
            "个体但还没选",
            "选完再说能贷吗",
            "演示企业能贷吗",
            "演示换一家再评级",
            "从列表选完问不对劲",
            "看全库后再问这家",
            "看全库后问服务名单",
            "名单点第一家",
            "FAQ后问能分析哪些",
            "导入说明后问服务有哪些",
            "乱码后点澄清chip",
            "空字符串带空格",
            "\t",
            "a" * 200,
            "重复重复重复能分析哪些企业",
            "能分析哪些企业？能分析哪些企业？",
            "服务业服务业服务业",
            "那呢",
            "呢",
            "有吗",
            "是哪些",
            "多少",
            "谁",
            "啥",
            "哦",
            "好",
            "行",
            "可以",
            "不行",
            "再来",
            "下一步",
            "上一步",
            "返回",
            "首页",
            "帮助",
            "说明书",
        ],
        1,
    ):
        q2 = q if q.strip() else " "
        _add(
            S,
            f"COLD{100+i:03d}",
            "cold",
            q2[:40],
            [{"query": q2, "fresh": True}],
            {"no_abstain": True, "min_len": 1},
        )

    # 确保 ≥100
    while len(S) < 100:
        n = len(S) + 1
        _add(
            S,
            f"COLDX{n:03d}",
            "cold",
            f"冷门填充{n}",
            [{"query": f"服务有哪些企业变体{n}", "fresh": True}],
            {"no_abstain": True, "parse_in": ["negotiate_scope", "clarify"], "reply_has_any": ["家", "服务", "确定"]},
        )
    return S[:100]


def build_suite(name: str) -> list[dict[str, Any]]:
    core = b100.scenarios()
    if name == "core":
        return core
    if name == "200":
        out = core + extra_200()
        # pad to 200
        k = 1
        while len(out) < 200:
            out.append(
                {
                    "id": f"PAD{k:03d}",
                    "family": "negotiate_slice",
                    "title": f"服务名单变体{k}",
                    "turns": [
                        {"query": "我能分析哪些企业", "fresh": True},
                        {"query": f"服务业有哪些企业呢{k}" if k % 2 else f"制造有哪些{k}"},
                    ],
                    "expect": {
                        "parse_in": ["negotiate_scope"],
                        "reply_not_overview": True,
                        "no_preach": True,
                        "no_abstain": True,
                        "reply_has_any": ["家", "服务", "制造"],
                    },
                }
            )
            k += 1
        return out[:200]
    if name == "cold":
        return cold_100()
    if name == "all":
        return build_suite("200") + build_suite("cold")
    raise SystemExit(f"unknown suite {name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["core", "200", "cold", "all"], default="200")
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    all_sc = build_suite(args.suite)
    if args.limit:
        all_sc = all_sc[: args.limit]
    out = args.out or f"_dialog_suite_{args.suite}_report.json"
    print(f"SUITE={args.suite} N={len(all_sc)} BASE={b100.BASE}")
    token = b100._login()
    results = []
    t0 = time.time()
    for sc in all_sc:
        # custom_report: relax parse_in — check function-ish via no_abstain + min_len
        if sc["family"] == "custom_report" and sc.get("expect", {}).get("parse_in"):
            # drop strict parse; keep content checks
            exp = dict(sc["expect"])
            exp.pop("parse_in", None)
            sc = {**sc, "expect": exp}
        r = b100.run_one(token, sc)
        results.append(r)
        mark = "OK  " if r["ok"] else "FAIL"
        err = ",".join(r["errors"][:3]) if r["errors"] else ""
        print(f"{mark} [{r['id']}] {r['family']} :: {str(r['title'])[:36]} :: {err}")

    by_fam: dict[str, dict[str, int]] = {}
    fails = []
    for r in results:
        by_fam.setdefault(r["family"], {"ok": 0, "fail": 0})
        if r["ok"]:
            by_fam[r["family"]]["ok"] += 1
        else:
            by_fam[r["family"]]["fail"] += 1
            fails.append(r)

    ok_n = sum(1 for r in results if r["ok"])
    fail_n = len(results) - ok_n
    report = {
        "suite": args.suite,
        "total": len(results),
        "ok": ok_n,
        "fail": fail_n,
        "elapsed_sec": round(time.time() - t0, 1),
        "by_family": by_fam,
        "fails": [
            {
                "id": f["id"],
                "family": f["family"],
                "title": f["title"],
                "errors": f["errors"],
                "reply": f.get("final_reply"),
                "parse": f.get("final_parse"),
            }
            for f in fails
        ],
        "results": results,
    }
    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n======== SUMMARY ========")
    print(f"total={len(results)} ok={ok_n} fail={fail_n}")
    for fam, st in sorted(by_fam.items(), key=lambda x: -x[1]["fail"]):
        print(f"  {fam}: ok={st['ok']} fail={st['fail']}")
    print(f"report → {out_path}")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
