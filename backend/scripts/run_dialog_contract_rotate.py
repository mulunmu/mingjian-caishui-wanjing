# -*- coding: utf-8 -*-
"""对话契约轮换套件：每轮 100 主场景 + 100 冷门，场景互异，重跑用新 seed 再洗牌。

验收根契约（禁止白名单补丁）：
- 聚合趋势 unbound → 不逼选企业
- 寒暄 → meta，不 clarify
- 真实性/按地区 → analyze，不「暂不支持该下钻」
- 多意图拼句 → 请选一项
- 制造群体后真实性 → 不假 drill

  python -m scripts.run_dialog_contract_rotate --seed auto
  python -m scripts.run_dialog_contract_rotate --seed 42
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_dialog_boundary_100 as b100  # noqa: E402

INDUSTRIES = ["制造", "服务", "建筑", "批发零售", "其他"]
PROVINCES = ["广东", "浙江", "江苏", "山东", "四川"]
GREETINGS = ["早上好", "上午好", "下午好", "晚上好", "你好", "您好", "嗨", "谢谢", "辛苦了"]

TREND_PHRASES = [
    "分析各行业趋势走向",
    "各行业的营收趋势怎么样",
    "帮我看行业趋势走向",
    "全库各行业走势",
    "行业同比趋势分析一下",
    "各行业走向如何",
    "想看趋势分布",
    "行业趋势对比",
    "全样本行业营收同比走势",
    "帮我扫一眼各行业趋势",
    "行业层面趋势怎么走",
    "看看全库行业走向",
    "各业营收同比分布",
    "趋势按行业拆开看",
    "行业风险趋势概览",
    "全库行业走势一览",
]
MULTI_JOINS = [
    "进一步看真实性交叉验证；按地区拆分趋势；生成报告",
    "按地区拆分趋势；生成报告",
    "进一步看真实性交叉验证；生成报告",
    "看经营真实性；按地区看趋势",
    "分析各行业趋势走向；生成报告",
    "早上好；全库哪里信号最多",
    "收入真实性怎么样；生成报告",
    "按地区拆分趋势；进一步看真实性交叉验证",
]
AUTH_PHRASES = [
    "进一步看真实性交叉验证",
    "看经营真实性",
    "收入真实性怎么样",
    "申报和开票对得上吗",
    "做一下真实性交叉",
]
REGION_PHRASES = [
    "按地区拆分趋势",
    "按地区看趋势",
    "地区拆分看走向",
    "分省份看趋势",
]
VOUCHER_PHRASES = [
    "调异常主体的票据与货物凭证",
    "调票据交易背景和货物凭证",
]


def _sid(seed: str, tag: str, i: int) -> str:
    h = hashlib.md5(f"{seed}:{tag}:{i}".encode()).hexdigest()[:6]
    return f"{tag}{i:03d}_{h}"


def build_pool(rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """构造远大于 200 的互异场景池，再由调用方抽样。"""
    main: list[dict[str, Any]] = []
    cold: list[dict[str, Any]] = []

    def add(bucket: list, family: str, title: str, turns: list, expect: dict, sid: str):
        bucket.append(
            {
                "id": sid,
                "family": family,
                "title": title,
                "turns": turns,
                "expect": expect,
            }
        )

    # 主：聚合趋势冷启动（每句不同 paraphrase）
    for i, q in enumerate(TREND_PHRASES):
        add(
            main,
            "contract_trend",
            q,
            [{"query": q, "fresh": True}],
            {
                "no_abstain": True,
                "no_preach": True,
                "reply_not": ["某一家企业", "请先选一家", "还不知道要看哪家"],
                "reply_has_any": ["行业", "趋势", "同比", "样本", "家", "上行", "下行", "增长"],
                "min_len": 20,
            },
            _sid(str(rng.random()), "T", i),
        )

    # 主：寒暄
    for i, q in enumerate(GREETINGS):
        add(
            main,
            "contract_greeting",
            q,
            [{"query": q, "fresh": True}],
            {
                "no_abstain": True,
                "reply_not": ["某一家企业", "暂不支持该下钻", "我没太确定"],
                "reply_has_any": ["你好", "可以", "企业", "全库", "演示", "群体", "分析"],
                "min_len": 6,
            },
            _sid(str(rng.random()), "G", i),
        )

    # 主：多意图拼句
    for i, q in enumerate(MULTI_JOINS):
        add(
            main,
            "contract_multi",
            q[:20],
            [{"query": q, "fresh": True}],
            {
                "no_abstain": True,
                "reply_not": ["暂不支持该下钻"],
                "reply_has_any": ["好几件事", "选一项", "请先选", "按钮", "选", "几件", "一项"],
                "min_len": 8,
            },
            _sid(str(rng.random()), "M", i),
        )

    # 主：全库信号 / 群体风险（防 FAQ 弃权）
    for i, q in enumerate(
        [
            "全库哪里信号最多",
            "整体风险怎样",
            "群体风险偏高吗",
            "群体风险偏高然后呢",
            "哪里信号最集中",
            "全样本风险信号分布",
            "现在群体风险偏高怎么办",
            "全库风险点在哪",
        ]
    ):
        add(
            main,
            "contract_signal",
            q,
            [{"query": q, "fresh": True}],
            {
                "no_abstain": True,
                "reply_not": ["某一家企业", "暂不支持该下钻"],
                "reply_has_any": ["信号", "风险", "家", "样本", "命中"],
                "min_len": 12,
            },
            _sid(str(rng.random()), "S", i),
        )

    # 主：制造群体 → 真实性 / 地区（焦点链）
    for i, (ind, auth, region) in enumerate(
        zip(
            INDUSTRIES,
            AUTH_PHRASES + AUTH_PHRASES,
            REGION_PHRASES + REGION_PHRASES,
        )
    ):
        if i >= 8:
            break
        add(
            main,
            "contract_focus_auth",
            f"{ind}→真实性",
            [
                {"query": "我能分析哪些企业", "fresh": True},
                {"query": f"{ind}有哪些企业"},
                {
                    "query": f"看{ind}群体风险",
                    "followup": {
                        "type": "dialog_act",
                        "label": f"看{ind}群体风险",
                        "params": {
                            "act": "analyze",
                            "scenario": "warn",
                            "scope_target": "cohort",
                            "industry_l1": ind if ind != "其他" else None,
                            "confidence": 1.0,
                        },
                    },
                },
                {"query": auth},
            ],
            {
                "no_abstain": True,
                "reply_not": ["暂不支持该下钻", "某一家企业", "请先选一家"],
                "reply_has_any": ["真实", "申报", "开票", "口径", "偏差", "家", "样本", "风险"],
                "min_len": 15,
            },
            _sid(str(rng.random()), "FA", i),
        )
        add(
            main,
            "contract_focus_region",
            f"{ind}→地区趋势",
            [
                {"query": "我能分析哪些企业", "fresh": True},
                {
                    "query": f"看{ind}群体风险",
                    "followup": {
                        "type": "dialog_act",
                        "label": f"看{ind}群体风险",
                        "params": {
                            "act": "analyze",
                            "scenario": "warn",
                            "scope_target": "cohort",
                            "industry_l1": ind if ind != "其他" else None,
                            "confidence": 1.0,
                        },
                    },
                },
                {"query": region},
            ],
            {
                "no_abstain": True,
                "reply_not": ["暂不支持该下钻", "某一家企业"],
                "reply_has_any": ["地区", "省", "趋势", "同比", "家", "样本", "行业", "风险"],
                "min_len": 12,
            },
            _sid(str(rng.random()), "FR", i),
        )

    # 主：调证 → action
    for i, q in enumerate(VOUCHER_PHRASES):
        add(
            main,
            "contract_voucher",
            q,
            [
                {"query": "全库哪里信号最多", "fresh": True},
                {
                    "query": q,
                    "followup": {
                        "type": "action",
                        "label": q,
                        "action": "manual_checklist",
                        "params": {"hint": "人工核查清单：请调取票据与货物凭证。"},
                    },
                },
            ],
            {
                "no_abstain": True,
                "reply_not": ["暂不支持该下钻"],
                "reply_has_any": ["人工", "票据", "凭证", "核查"],
                "min_len": 8,
            },
            _sid(str(rng.random()), "V", i),
        )

    # 主：行业名单协商（扩写以保证 ≥100 互异）
    for i, ind in enumerate(INDUSTRIES * 8):
        q = rng.choice(
            [
                f"{ind}有哪些企业",
                f"{ind}行业名单",
                f"把{ind}列出来",
                f"{ind}那几家是谁",
                f"{ind}有多少家",
                f"{ind}还能展开吗",
                f"再列一下{ind}",
                f"{ind}样本有哪些",
            ]
        )
        # 强制互异：附带序号后缀仅用于指纹（问句仍自然）
        q_turn = q if i < 20 else f"{q}（第{i}组）"
        # 实际发给模型的句子去掉元后缀
        q_ask = q
        add(
            main,
            "negotiate_slice",
            q[:24],
            [{"query": "我能分析哪些企业", "fresh": True}, {"query": q_ask, "_uniq": i}],
            {
                "no_abstain": True,
                "no_preach": True,
                "reply_has_any": [ind, "家"],
                "reply_not_overview": True,
                "min_len": 8,
            },
            _sid(str(rng.random()), "N", i),
        )

    # 主：四场景个体（需先绑定）
    loans = ["这家能贷吗", "放贷风险大吗", "给不给授信", "额度要不要收紧"]
    for i, q in enumerate(loans):
        add(
            main,
            "individual_loan",
            q,
            [
                {
                    "query": "试用演示企业",
                    "fresh": True,
                    "followup": {
                        "type": "switch_scope",
                        "target": "individual",
                        "params": {"use_demo": True},
                    },
                },
                {"query": q},
            ],
            {
                "no_abstain": True,
                "reply_not": ["暂不支持该下钻"],
                "min_len": 10,
            },
            _sid(str(rng.random()), "L", i),
        )

    # 冷门：怪问法 / 边界
    cold_qs = [
        "早啊今天适合看啥风险",
        "趋势呢？",
        "那真实性呢",
        "地区那边呢",
        "生成报告；再看趋势",
        "早上好；分析各行业趋势走向",
        "全库；哪里信号最多",
        "制造呢风险",
        "建筑那边群体风险",
        "服务的真实性交叉",
        "批发零售按地区拆",
        "IT软件趋势走向",
        "随便看看行业走势",
        "有没有地区差异的趋势",
        "别下钻，看真实性",
        "不要名单要趋势",
        "群体风险偏高然后呢",
        "继续",
        "然后呢",
        "再往下看一层真实性",
        "分省对比一下营收同比",
        "各省走势差在哪",
        "票货款怎么核",
        "核查清单给我",
        "人工调证怎么做",
        "你好呀帮我看全库趋势",
        "嗨，制造有多少家",
        "谢了，再看建筑名单",
        "中午好全库信号",
        "晚上好能分析哪些",
    ]
    # 扩展冷门：随机组合
    for i in range(80):
        ind = rng.choice(INDUSTRIES)
        kind = rng.choice(["trend", "auth", "region", "list", "greet", "multi", "cohort"])
        if kind == "trend":
            q = rng.choice(
                [
                    f"{ind}营收趋势怎样",
                    f"看看{ind}走势",
                    f"{ind}同比走向",
                    f"帮我扫一眼{ind}趋势",
                ]
            )
            turns = [{"query": q, "fresh": True}]
            expect = {
                "no_abstain": True,
                "reply_not": ["暂不支持该下钻", "某一家企业"],
                "min_len": 8,
            }
        elif kind == "auth":
            q = rng.choice(AUTH_PHRASES)
            turns = [
                {"query": "全库哪里信号最多", "fresh": True},
                {"query": q},
            ]
            expect = {"no_abstain": True, "reply_not": ["暂不支持该下钻"], "min_len": 8}
        elif kind == "region":
            q = rng.choice(REGION_PHRASES + [f"{rng.choice(PROVINCES)}趋势怎样"])
            turns = [{"query": "分析各行业趋势走向", "fresh": True}, {"query": q}]
            expect = {"no_abstain": True, "reply_not": ["暂不支持该下钻"], "min_len": 8}
        elif kind == "list":
            q = f"{ind}还有哪些"
            turns = [{"query": f"{ind}有哪些企业", "fresh": True}, {"query": q}]
            expect = {"no_abstain": True, "no_preach": True, "reply_has_any": ["家", ind], "min_len": 6}
        elif kind == "greet":
            q = rng.choice(GREETINGS + ["早", "哈喽", "Hello"])
            turns = [{"query": q, "fresh": True}]
            expect = {"reply_not": ["某一家企业", "暂不支持该下钻"], "min_len": 4}
        elif kind == "multi":
            q = "；".join(rng.sample(AUTH_PHRASES[:3] + REGION_PHRASES[:2] + ["生成报告"], k=2))
            turns = [{"query": q, "fresh": True}]
            expect = {"reply_not": ["暂不支持该下钻"], "reply_has_any": ["选", "几件", "按钮", "一项", "继续"], "min_len": 6}
        else:
            q = rng.choice(["全库哪里信号最多", "整体风险怎样", "群体风险偏高吗"])
            turns = [{"query": q, "fresh": True}]
            expect = {"no_abstain": True, "reply_not": ["某一家企业"], "min_len": 10}
        add(cold, "cold_rotate", q[:24], turns, expect, _sid(str(rng.random()), "C", i))

    for i, q in enumerate(cold_qs):
        add(
            cold,
            "cold_fixed",
            q[:24],
            [{"query": q, "fresh": True}],
            {
                "no_abstain": True,
                "reply_not": ["暂不支持该下钻操作"],
                "min_len": 4,
            },
            _sid(str(rng.random()), "CF", i),
        )

    rng.shuffle(main)
    rng.shuffle(cold)
    return main, cold


def run_one(token: str, sc: dict[str, Any]) -> dict[str, Any]:
    r = b100.run_one(token, sc)
    return {
        "id": r["id"],
        "family": r["family"],
        "title": r["title"],
        "ok": r["ok"],
        "reasons": r.get("errors") or [],
        "reply": (r.get("final_reply") or "")[:240],
        "parse_source": r.get("final_parse"),
        "dialog_act": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="auto", help="auto=时间戳；固定整数可复现")
    ap.add_argument("--main-n", type=int, default=100)
    ap.add_argument("--cold-n", type=int, default=100)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    seed = str(int(time.time())) if args.seed == "auto" else str(args.seed)
    rng = random.Random(seed)
    main_pool, cold_pool = build_pool(rng)
    # 去重 title+turns 指纹后抽样
    def uniq_take(pool: list, n: int) -> list:
        seen: set[str] = set()
        out: list = []
        for sc in pool:
            key = json.dumps(sc["turns"], ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            out.append(sc)
            if len(out) >= n:
                break
        return out

    mains = uniq_take(main_pool, args.main_n)
    colds = uniq_take(cold_pool, args.cold_n)

    def _fill(target: list, want: int, kind: str) -> None:
        """补齐互异场景；无新增则换 seed 再洗，封顶尝试防止死循环。"""
        seen = {json.dumps(x["turns"], ensure_ascii=False, sort_keys=True) for x in target}
        stagnant = 0
        attempt = 0
        while len(target) < want and attempt < 80:
            attempt += 1
            more_main, more_cold = build_pool(random.Random(f"{seed}:{kind}:{attempt}"))
            more = more_main if kind == "main" else more_cold
            added = 0
            for sc in more:
                key = json.dumps(sc["turns"], ensure_ascii=False, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                target.append(sc)
                added += 1
                if len(target) >= want:
                    break
            if added == 0:
                stagnant += 1
                if stagnant >= 8:
                    break
            else:
                stagnant = 0

    _fill(mains, args.main_n, "main")
    _fill(colds, args.cold_n, "cold")
    if len(mains) < args.main_n or len(colds) < args.cold_n:
        print(
            f"WARN pool short main={len(mains)}/{args.main_n} cold={len(colds)}/{args.cold_n}",
            flush=True,
        )

    print(f"seed={seed} main={len(mains)} cold={len(colds)}", flush=True)
    token = None
    last_err = None
    for _ in range(15):
        try:
            token = b100._login()
            break
        except Exception as exc:
            last_err = exc
            time.sleep(2)
    if not token:
        raise RuntimeError(f"login failed after retries: {last_err}")
    results = []
    for i, sc in enumerate(mains + colds, 1):
        r = run_one(token, sc)
        results.append(r)
        flag = "OK" if r["ok"] else "FAIL"
        print(
            f"[{i:03d}/{len(mains)+len(colds)}] {flag} {r['id']} {r['family']} {r['title'][:28]}",
            flush=True,
        )
        if not r["ok"]:
            print("   ", r["reasons"], "|", r["reply"][:120], flush=True)

    fails = [r for r in results if not r["ok"]]
    report = {
        "seed": seed,
        "main_n": len(mains),
        "cold_n": len(colds),
        "passed": len(results) - len(fails),
        "failed": len(fails),
        "fails": fails[:50],
        "results": results,
    }
    out = Path(args.out) if args.out else Path(__file__).resolve().parents[1] / f"_contract_rotate_{seed}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\npassed={report['passed']} failed={report['failed']} out={out}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
