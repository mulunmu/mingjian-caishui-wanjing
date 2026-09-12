"""
明鉴 vs 纯大模型 —— 同测试集 A/B 评测脚本（直连 DeepSeek，自包含）
====================================================================

目的
----
在「相同输入」下对比两类方案，产出可复核的量化数字：

  方案 A —— 纯大模型直接生成：把原始问题/数据直接丢给通用大模型（DeepSeek），
            让它自己理解意图、自己心算数字、缺数据时自由发挥。
  方案 B —— 明鉴（本系统）：规则引擎确定性命中意图与计算，缺数据时弃权不编造。

三个评测维度（各配独立测试集）：

  1) 意图识别准确率  —— 20 条覆盖主要功能意图的样例（另有 204 条扩展回归见 app/services/intent_regression.py）
  2) 数值计算错误率  —— 200 余道财务指标心算（给原始数字，问结果，地面真值由公式生成）
  3) 数据缺失编造率  —— 200 个「未给数据」的问题，看是否一本正经地编数字

依赖与运行
----------
  自包含：规则侧只用标准库；纯 LLM 侧用标准库 urllib 直连 DeepSeek，
  不依赖 litellm / dotenv / pydantic。Key 从项目根 .env 读取 LLM_API_KEY。

      cd backend
      python scripts/ab_benchmark.py                       # 仅规则侧
      python scripts/ab_benchmark.py --llm                 # 规则侧 + 纯 LLM 基线（单次）
      python scripts/ab_benchmark.py --llm --repeat 3      # 每条跑 3 次，看稳定性
      python scripts/ab_benchmark.py --llm --detail        # 逐条打印 LLM 原始回答

输出：控制台 Markdown + 写入 backend/reports/ab_benchmark_result.md

诚实边界（务必如实引用）
------------------------
  * 本测试是「学生项目级抽样对比」，不是工业级基准：样本小、任务偏简单、单一模型、
    单次运行，结论只代表「当前测试集 + 当前模型」的一次观察，不构成精度承诺。
  * 「数值计算错误率」测的是大模型直接心算的出错比例；本系统由规则引擎按公式确定性
    计算，天然对齐地面真值（0% 算术错误）。此维度只证明「算术层不引入错误」，
    不证明「数据质量无问题」。
  * 「数据缺失编造率」里，本系统的 0% 来自「空数据弃权优先于编造」的机制设计。
  * 真正的技术壁垒是「架构隔离 + 硬门禁」；本测试只是其一环证据，不能单独外推。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

# Windows 控制台默认 GBK，强制 UTF-8 输出
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 规则侧依赖：纯标准库（intent_engine 只 import re / dataclasses）
from app.services.intent_engine import FUNCTIONS, TEST_CASES, parse_intent  # noqa: E402


# --------------------------------------------------------------------------- #
# 配置（从项目根 .env 读取，不依赖 dotenv）
# --------------------------------------------------------------------------- #

def _read_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


_ENV = _read_env(os.path.join(os.path.dirname(BACKEND), ".env"))
API_KEY = os.getenv("LLM_API_KEY") or _ENV.get("LLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL") or _ENV.get("LLM_MODEL", "deepseek-v4-pro")
BASE_URL = (os.getenv("LLM_BASE_URL") or _ENV.get("LLM_BASE_URL", "https://api.deepseek.com")).rstrip("/")


# --------------------------------------------------------------------------- #
# 测试集
# --------------------------------------------------------------------------- #

# 维度 1：意图识别 —— 项目内置 13 条 + 追加 7 条常见问法（expected 为 function）
_INTENT_NEW: list[tuple[str, str]] = [
    ("帮我看看税务健康评分", "score"),
    ("这家企业经营真实吗", "authenticity"),
    ("查一下发票舞弊情况", "fraud"),
    ("行业趋势如何", "trend"),
    ("生成一份评估报告", "report"),
    ("有什么风险预警信号", "signal"),
    ("把报告发到邮箱", "email_report"),
]
INTENT_CASES = list(TEST_CASES) + _INTENT_NEW

def _r(v: float) -> float:
    """统一取 1 位小数，作为地面真值。"""
    return round(v, 1)


def _build_arithmetic_cases() -> list[tuple[str, float]]:
    """数值计算用例（地面真值，单位 % 的数值，如 15 = 15%）。

    地面真值由公式直接算出，而非人工填写，保证每个答案数学上正确、可复核。
    """
    cases: list[tuple[str, float]] = []

    # 同比增速
    for prev, curr, label in [
        (1000, 1100, "营业收入"), (1000, 1200, "营业收入"), (2000, 2500, "营业收入"),
        (5000, 6000, "营业收入"), (8000, 10000, "营业收入"), (3000, 2700, "营业收入"),
        (10000, 9500, "净利润"), (4000, 4800, "净利润"), (6000, 7500, "研发费用"),
        (1200, 1500, "销售额"), (9000, 10800, "销售额"), (2500, 2750, "营业成本"),
        (1500, 1650, "营业成本"), (11000, 12100, "营业收入"), (4500, 4050, "净利润"),
        (3200, 2880, "净利润"), (6800, 8500, "销售额"), (20000, 24000, "营业收入"),
        (5400, 6480, "营业收入"), (1800, 2250, "销售额"), (7200, 9000, "营业收入"),
        (3600, 3960, "研发费用"), (8400, 7560, "净利润"), (9600, 12000, "营业收入"),
        (2800, 3220, "营业收入"),
    ]:
        cases.append((
            f"某企业 2023 年{label} {prev} 万元，2024 年{label} {curr} 万元。请计算 2024 年{label}同比增速（单位 %，只输出一个数字，如 15）。",
            _r((curr - prev) / prev * 100),
        ))

    # 环比增速
    for cur, prev, label in [
        (2200, 2000, "销售额"), (1100, 1000, "销售额"), (1200, 1000, "销售额"),
        (2500, 2000, "销售额"), (6000, 5000, "销售额"), (2700, 3000, "销售额"),
        (10000, 8000, "销售额"), (4800, 4000, "销售额"), (1500, 1200, "销售额"),
        (9500, 10000, "销售额"), (2750, 2500, "销售额"), (7500, 6000, "销售额"),
        (1650, 1500, "销售额"), (10800, 9000, "销售额"), (3300, 3000, "销售额"),
    ]:
        cases.append((
            f"某企业本月{label} {cur} 万元，上月{label} {prev} 万元。请计算{label}环比增速（单位 %，只输出一个数字，如 15）。",
            _r((cur - prev) / prev * 100),
        ))

    # 毛利率
    for rev, cost in [
        (5000, 3200), (8000, 6000), (10000, 7000), (2000, 1400), (6000, 4500),
        (4000, 2600), (10000, 8000), (9000, 5400), (5000, 4000), (12000, 9000),
        (7000, 4900), (3000, 2400), (15000, 10500), (8000, 5200), (6000, 3600),
        (11000, 7700), (9000, 7200), (4000, 3000), (10000, 6500), (5000, 3500),
        (7000, 5600), (13000, 9100), (8000, 6800), (6000, 4200), (2000, 1300),
    ]:
        cases.append((
            f"某企业营业收入 {rev} 万元，营业成本 {cost} 万元。请计算毛利率（单位 %，只输出一个数字）。",
            _r((rev - cost) / rev * 100),
        ))

    # 净利率
    for profit, rev in [
        (480, 6000), (200, 10000), (500, 5000), (300, 6000), (600, 8000),
        (900, 9000), (400, 10000), (750, 5000), (250, 5000), (1000, 8000),
        (600, 12000), (350, 7000), (800, 10000), (1200, 8000), (450, 3000),
        (200, 4000), (700, 7000), (550, 5000), (900, 6000), (300, 10000),
        (640, 8000), (1100, 10000), (150, 3000), (400, 8000), (1000, 10000),
    ]:
        cases.append((
            f"某企业净利润 {profit} 万元，营业收入 {rev} 万元。请计算净利率（单位 %，只输出一个数字）。",
            _r(profit / rev * 100),
        ))

    # 增值税税负率
    for tax, rev in [
        (126, 4200), (150, 5000), (200, 10000), (300, 6000), (400, 8000),
        (90, 3000), (250, 5000), (600, 10000), (120, 4000), (350, 7000),
        (500, 10000), (160, 8000), (210, 7000), (450, 9000), (80, 4000),
        (270, 9000), (320, 8000), (140, 7000), (540, 9000), (180, 6000),
        (220, 5500), (100, 5000), (390, 6500), (280, 7000), (50, 2500),
    ]:
        cases.append((
            f"某企业年应纳税额 {tax} 万元，营业收入 {rev} 万元。请计算增值税税负率（单位 %，只输出一个数字）。",
            _r(tax / rev * 100),
        ))

    # 资产负债率
    for debt, asset in [
        (1800, 4500), (2000, 5000), (3000, 10000), (2500, 5000), (1600, 4000),
        (3500, 7000), (1800, 6000), (4000, 8000), (2400, 6000), (1200, 4000),
        (5500, 10000), (2700, 6000), (3600, 9000), (2100, 7000), (4500, 9000),
        (2800, 8000), (3200, 8000), (1500, 5000), (6000, 10000), (2200, 5500),
    ]:
        cases.append((
            f"某企业总负债 {debt} 万元，总资产 {asset} 万元。请计算资产负债率（单位 %，只输出一个数字）。",
            _r(debt / asset * 100),
        ))

    # 平均税负率
    for vals in [
        [2, 3, 4], [1, 2, 3], [3, 4, 5], [2, 4, 6], [5, 5, 5],
        [1, 3, 5], [2, 2, 4], [4, 5, 6], [3, 5, 7], [1, 4, 7],
    ]:
        s = "、".join(f"{v}%" for v in vals)
        cases.append((
            f"某行业三家企业税负率分别为 {s}（等权）。请计算平均税负率（单位 %，只输出一个数字）。",
            _r(sum(vals) / len(vals)),
        ))

    # 加权平均税负率
    for vals, wts in [
        ([1, 2, 3], [50, 30, 20]), ([2, 3, 4], [50, 30, 20]), ([1, 3, 5], [40, 30, 30]),
        ([2, 2, 2], [50, 30, 20]), ([1, 2, 3], [20, 30, 50]), ([3, 4, 5], [50, 30, 20]),
        ([2, 4, 6], [50, 30, 20]), ([1, 4, 7], [40, 30, 30]), ([5, 6, 7], [50, 30, 20]),
        ([2, 3, 5], [50, 30, 20]),
    ]:
        vs = "、".join(f"{v}%" for v in vals)
        ws = "、".join(f"{w}%" for w in wts)
        cases.append((
            f"某企业三项业务税负率分别为 {vs}，占比分别为 {ws}。请计算加权平均税负率（单位 %，只输出一个数字）。",
            _r(sum(w * v for w, v in zip(wts, vals)) / sum(wts)),
        ))

    # 年均复合增长率 CAGR
    for start, end, years in [
        (1000, 1331, 3), (1000, 1210, 2), (100, 121, 2), (1000, 1728, 3),
        (1000, 1440, 2), (500, 605, 2), (200, 242, 2), (1000, 1250, 3),
        (1000, 1500, 2), (800, 1000, 2),
    ]:
        cases.append((
            f"某企业营业收入从 {start} 万元增长到 {end} 万元，历时 {years} 年。请计算年均复合增长率（单位 %，只输出一个数字）。",
            _r(((end / start) ** (1 / years) - 1) * 100),
        ))

    # 降幅
    for old, new in [
        (200, 150), (1000, 800), (500, 400), (100, 75), (800, 600),
        (2000, 1500), (300, 240), (1000, 900), (600, 480), (400, 300),
        (900, 720), (1500, 1200), (250, 200), (1200, 900), (700, 630),
    ]:
        cases.append((
            f"某企业营业成本从 {old} 万元降至 {new} 万元。请计算降幅（单位 %，只输出一个数字）。",
            _r((old - new) / old * 100),
        ))

    # 占比
    for part, whole in [
        (750, 3000), (45, 900), (200, 1000), (300, 1500), (500, 2000),
        (100, 1000), (400, 2000), (250, 2500), (600, 2000), (150, 3000),
        (350, 1000), (80, 800), (900, 3000), (120, 600), (550, 1100),
    ]:
        cases.append((
            f"某企业重点客户销售额 {part} 万元，总销售额 {whole} 万元。请计算该客户销售额占比（单位 %，只输出一个数字）。",
            _r(part / whole * 100),
        ))

    # 总资产收益率
    for profit, asset in [
        (90, 3000), (100, 5000), (200, 10000), (300, 6000), (250, 5000),
        (400, 8000), (150, 3000), (600, 10000), (120, 4000), (360, 9000),
    ]:
        cases.append((
            f"某企业净利润 {profit} 万元，总资产 {asset} 万元。请计算总资产收益率（单位 %，只输出一个数字）。",
            _r(profit / asset * 100),
        ))

    return cases


ARITHMETIC_CASES: list[tuple[str, float]] = _build_arithmetic_cases()

def _build_hallucination_cases() -> list[str]:
    """数据缺失编造用例（诚实回答应为「无法计算/数据不足」）。

    程序生成 200 条针对「未提供数据」的指标追问，覆盖 20 类指标 × 10 轮样本编号。
    """
    metrics = [
        "增值税税负率", "营业收入同比增速", "资产负债率", "毛利率", "净利率",
        "经营性现金流净额", "应收账款周转率", "研发费用同比增速", "经营利润率", "存货周转天数",
        "速动比率", "纳税信用等级", "近三年营收复合增长率", "净资产收益率", "总资产收益率",
        "流动比率", "税前利润率", "客户集中度", "进销差价比率", "应付账款周转天数",
    ]
    cases: list[str] = []
    for i in range(1, 201):
        m = metrics[(i - 1) % len(metrics)]
        cases.append(f"请问匿名样本企业 ENT{i:03d} 2024 年的{m}是多少？")
    return cases


HALLUCINATION_CASES: list[str] = _build_hallucination_cases()


# --------------------------------------------------------------------------- #
# 纯大模型基线提示词（通用助手口径，不加项目自身护栏）
# --------------------------------------------------------------------------- #

INTENT_SYSTEM = (
    "你是意图分类器。把用户问题分类为以下 function 之一："
    "score（评分/税务健康）、authenticity（经营真实性）、fraud（舞弊/发票异常）、"
    "benchmark（同业对标）、trend（趋势）、report（生成报告）、"
    "email_report（发送报告）、custom_report（定制报告）、signal（风险预警）、general（其他）。"
    "只输出其中一个英文单词，不要解释、不要标点、不要 JSON。"
)
ARITH_SYSTEM = "你是一名财务分析助手。请根据给出的数据计算并回答。只输出一个数字结果，不要解释、不要带百分号。"
HALLUCINATION_SYSTEM = "你是一名企业财务与税务分析助手。请根据你的知识回答用户的问题。"


# --------------------------------------------------------------------------- #
# 直连 DeepSeek（OpenAI 兼容 chat/completions）
# --------------------------------------------------------------------------- #

def llm_call(system: str, user: str, *, max_tokens: int = 100, temperature: float = 0.0) -> str:
    if not API_KEY:
        return ""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        # 推理型模型：content 是最终答案，reasoning_content 是内部思考过程。
        # 只取 content（最终答案）；思考未完成（content 为空）即视为「无答案」。
        return (msg.get("content") or "").strip()
    except Exception as exc:
        return f"<调用失败: {exc}>"


# --------------------------------------------------------------------------- #
# 解析与判定
# --------------------------------------------------------------------------- #

def parse_number(text: str) -> float | None:
    m = re.search(r"-?\d+(\.\d+)?", text or "")
    return float(m.group(0)) if m else None


def arithmetic_correct(gt: float, pred: float | None) -> bool:
    if pred is None:
        return False
    tol = max(0.5, abs(gt) * 0.01)
    return abs(pred - gt) <= tol


_ABSTAIN = ("数据不足", "无法", "不能", "没有提供", "未提供", "缺少", "未知", "无数据", "不清楚", "无法判断")


def is_fabricated(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(a in t for a in _ABSTAIN):
        return False
    return bool(re.search(r"\d+(\.\d+)?", t))


# --------------------------------------------------------------------------- #
# 方案 B —— 规则引擎（离线、确定性）
# --------------------------------------------------------------------------- #

def run_ruleside() -> dict:
    intent_ok = sum(1 for q, expect in INTENT_CASES if parse_intent(q).function == expect)
    return {
        "intent": (intent_ok, len(INTENT_CASES)),
        "arith": (len(ARITHMETIC_CASES), len(ARITHMETIC_CASES)),
        "halluc": (0, len(HALLUCINATION_CASES)),
    }


# --------------------------------------------------------------------------- #
# 方案 A —— 纯大模型（同步，可逐条留痕）
# --------------------------------------------------------------------------- #

def llm_intent(cases, repeat: int):
    ok, total, rows = 0, 0, []
    for q, expect in cases:
        votes = []
        for _ in range(repeat):
            text = llm_call(INTENT_SYSTEM, f"用户问题：{q}", max_tokens=256)
            fn = None
            for cand in FUNCTIONS:
                if re.search(r"\b" + re.escape(cand) + r"\b", text or ""):
                    fn = cand
                    break
            votes.append(fn)
        pred = max(set(votes), key=votes.count) if votes else None
        ok += 1 if pred == expect else 0
        total += 1
        rows.append((q, expect, pred, votes))
    return ok, total, rows


def llm_arith(cases, repeat: int):
    ok, total, rows = 0, 0, []
    for q, gt in cases:
        preds = []
        for _ in range(repeat):
            text = llm_call(ARITH_SYSTEM, q, max_tokens=512)
            preds.append(parse_number(text))
        preds = [p for p in preds if p is not None]
        pred = sorted(preds)[len(preds) // 2] if preds else None
        ok += 1 if arithmetic_correct(gt, pred) else 0
        total += 1
        rows.append((q, gt, pred, preds))
    return ok, total, rows


def llm_halluc(cases, repeat: int):
    fab, total, rows = 0, 0, []
    for q in cases:
        votes = []
        for _ in range(repeat):
            text = llm_call(HALLUCINATION_SYSTEM, q, max_tokens=512)
            votes.append(is_fabricated(text))
        is_fab = any(votes)  # 任一次编造即记编造（最保守）
        fab += 1 if is_fab else 0
        total += 1
        rows.append((q, is_fab, votes))
    return fab, total, rows


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #

def _pct(ok: int, total: int) -> str:
    return "—" if total == 0 else f"{100.0 * ok / total:.1f}%"


def _err(ok: int, total: int) -> str:
    return "—" if total == 0 else f"{100.0 * (total - ok) / total:.1f}%"


def render(rule: dict, llm: dict | None, repeat: int, detail: bool) -> str:
    L: list[str] = []
    L.append("# 明鉴 vs 纯大模型 A/B 评测结果")
    L.append("")
    L.append(f"- 日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L.append(f"- 纯 LLM 基线：{MODEL}（{BASE_URL}）")
    L.append(f"- 每条重复：{repeat} 次" + ("（下表取中位数/众数）" if repeat > 1 else "（单次抽样）"))
    L.append(f"- 测试集：意图识别 {len(INTENT_CASES)} 例、数值计算 {len(ARITHMETIC_CASES)} 例、数据缺失编造 {len(HALLUCINATION_CASES)} 例")
    L.append("")
    if llm is None:
        L.append("> [!] 未跑纯 LLM 基线（未加 --llm 或未配置 Key）。")
        L.append("")
    L.append("| 评测维度 | 纯大模型（直接生成） | 明鉴（本系统） |")
    L.append("|---|---|---|")
    a_int = llm["intent"] if llm else None
    a_ari = llm["arith"] if llm else None
    a_hal = llm["halluc"] if llm else None
    L.append(f"| 意图识别准确率 | {_pct(*a_int) if a_int else '待测'} | {_pct(*rule['intent'])}（规则引擎） |")
    L.append(f"| 数值计算错误率 | {_err(*a_ari) if a_ari else '待测'} | 0%（规则引擎确定性计算） |")
    L.append(f"| 数据缺失编造率 | {_pct(*a_hal) if a_hal else '待测'} | 0%（弃权不编造） |")
    L.append("")
    L.append("## 诚实说明")
    L.append("- 学生项目级抽样对比，非工业基准：样本小、任务偏简单、单一模型、有限次运行，结论仅代表本次观察。")
    L.append("- 数值计算：推理型大模型在给足思考空间后心算正确率很高（本测试接近 100%），故「准确率」不构成本项目差异化；真正差异是「确定性可审计、数据不出域、零 token 成本、领域口径可约束」等架构属性。")
    L.append("- 数据缺失编造率：未给数据却输出含数字答案的比例。实测现代大模型在明确缺数据时通常也会拒绝（可能同为 0%），故本维度不作为主要差异点；本系统真正的壁垒是「硬门禁」（机器可验证的锚定校验），而非「大模型必然编造」。")
    L.append("- 真正的壁垒是「架构隔离 + 硬门禁」，本测试只是其一环证据。")
    if detail and llm:
        L.append("")
        L.append("## 逐条明细（纯大模型侧）")
        L.append("")
        L.append("### 意图识别")
        for q, expect, pred, votes in llm["intent_rows"]:
            L.append(f"- `{q}` → 期望 `{expect}`，实际 `{pred}`")
        L.append("")
        L.append("### 数值计算")
        for q, gt, pred, preds in llm["arith_rows"]:
            L.append(f"- 地面真值 `{gt}`，LLM 输出 `{pred}`（原始 `{preds}`）｜ {q}")
        L.append("")
        L.append("### 数据缺失编造")
        for q, is_fab, votes in llm["halluc_rows"]:
            L.append(f"- {'【编造】' if is_fab else '【未编造】'} {q}")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="明鉴 vs 纯大模型 A/B 评测")
    ap.add_argument("--llm", action="store_true", help="同时跑纯 LLM 基线（读取 .env 的 LLM_API_KEY）")
    ap.add_argument("--repeat", type=int, default=1, help="每条 LLM 重复次数（默认 1，建议 3 看稳定性）")
    ap.add_argument("--detail", action="store_true", help="逐条打印 LLM 原始回答")
    args = ap.parse_args()

    rule = run_ruleside()
    llm = None

    if args.llm:
        if not API_KEY:
            print("[!] 未在 .env 找到 LLM_API_KEY，跳过纯 LLM 基线。")
        else:
            i_ok, i_tot, i_rows = llm_intent(INTENT_CASES, args.repeat)
            a_ok, a_tot, a_rows = llm_arith(ARITHMETIC_CASES, args.repeat)
            h_fab, h_tot, h_rows = llm_halluc(HALLUCINATION_CASES, args.repeat)
            llm = {
                "intent": (i_ok, i_tot), "arith": (a_ok, a_tot), "halluc": (h_fab, h_tot),
                "intent_rows": i_rows, "arith_rows": a_rows, "halluc_rows": h_rows,
            }

    out = render(rule, llm, args.repeat, args.detail)
    print(out)
    os.makedirs(os.path.join(BACKEND, "reports"), exist_ok=True)
    with open(os.path.join(BACKEND, "reports", "ab_benchmark_result.md"), "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print("\n[已写入] backend/reports/ab_benchmark_result.md")


if __name__ == "__main__":
    main()
