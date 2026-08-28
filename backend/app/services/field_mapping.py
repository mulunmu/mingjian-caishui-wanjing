"""四层字段映射引擎（阶段二 · 数据接入口径统一）。

借鉴 Granit.DataExchange 四层映射：已存(saved) → 精确(exact) → 模糊(fuzzy) → LLM 语义(llm)。
前三层纯本地、确定性、零 LLM 成本；LLM 只在模糊层置信度不足时兜底，且只发表头元数据（列名），
不发任何原始数据 / PII（对齐 querychat 数据字典模式）。
"""
from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# 目标源字段的中英别名（口径统一引导）。值越靠前越优先。
FIELD_ALIASES: dict[str, list[str]] = {
    "industry_l1": ["行业大类", "行业", "一级行业", "industry", "industry_l1", "industry l1"],
    "industry_l2": ["行业细类", "二级行业", "细分行业", "industry_l2", "industry l2"],
    "province": ["省份", "省", "province", "所在省"],
    "city": ["城市", "市", "city", "所在市"],
    "scale_label": ["企业规模", "规模", "规模标签", "scale", "scale_label"],
    "credit_score": ["纳税信用分", "信用分", "信用评级分", "纳税信用", "credit_score", "credit score"],
    "tax_on_time_rate": ["纳税准时率", "准时率", "按时纳税率", "on_time_rate", "tax_on_time_rate"],
    "tax_arrears_cnt": ["欠税条数", "欠税次数", "欠税记录", "欠税", "arrears", "tax_arrears_cnt"],
    "tax_violation_cnt": ["税务违法次数", "税务违法", "违法次数", "税务违规", "violation", "tax_violation_cnt"],
    "high_severity_cnt": ["高危事件次数", "高危事件", "严重违法次数", "high_severity", "high_severity_cnt"],
    "is_dishonesty": ["是否失信", "失信标志", "失信", "dishonesty", "is_dishonesty"],
    "is_execution": ["是否被执行", "被执行", "被执行标志", "execution", "is_execution"],
    "vat_revenue": ["增值税营收", "增值税收入", "增值税", "销项营收", "vat", "vat_revenue"],
    "invoice_revenue": ["发票营收", "发票收入", "开票金额", "开票营收", "invoice", "invoice_revenue"],
    "finance_revenue": ["财务营收", "财务收入", "营业收入", "主营收入", "revenue", "finance_revenue"],
    "revenue_deviation": ["营收偏差", "营收口径偏差", "口径偏差", "偏差率", "deviation", "revenue_deviation"],
    "invoice_monthly_avg": ["月均开票额", "月均开票", "月开票额", "monthly_avg", "invoice_monthly_avg"],
    "invoice_cnt": ["开票张数", "发票张数", "开票数量", "invoice_cnt", "invoice count"],
    "red_invoice_cnt": ["红字发票张数", "红字发票", "红冲", "红字", "red_invoice", "red_invoice_cnt"],
    "profit_margin": ["利润率", "净利率", "净利润率", "margin", "profit_margin"],
    "revenue_yoy": ["营收同比", "收入同比", "营收增速", "revenue_yoy", "revenue yoy", "yoy"],
    "profit_yoy": ["利润同比", "利润增速", "profit_yoy", "profit yoy"],
    "debt_ratio": ["资产负债率", "负债率", "debt_ratio", "debt ratio"],
    "cash_flow_net": ["净现金流", "经营现金流", "现金流", "cash_flow", "cash_flow_net"],
    "cash_flow_level": ["现金流水平", "现金流标签", "cash_flow_level"],
}

FUZZY_THRESHOLD = 0.72  # 模糊层最低相似度
LLM_MIN_CONFIDENCE = 0.60  # 低于此置信度才路由 LLM


def normalize(name: str) -> str:
    """归一化列名：小写 + 去空白/下划线/连字符/标点。"""
    s = (name or "").lower().strip()
    for ch in " _-—．.·/（）()【】[]{}:：,，;；":
        s = s.replace(ch, "")
    return s


def _build_vocab() -> dict[str, str]:
    """field -> 归一化候选串（字段名 + 别名，去重保序）。"""
    vocab: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        norm = [normalize(a) for a in [field, *aliases]]
        seen: set[str] = set()
        ordered = []
        for n in norm:
            if n and n not in seen:
                seen.add(n)
                ordered.append(n)
        vocab[field] = ordered
    return vocab


_VOCAB = _build_vocab()


def _saved_match(normalized: str, saved: dict[str, str] | None) -> str | None:
    if not saved:
        return None
    return saved.get(normalized) or saved.get(normalize(normalized))


def _exact_match(normalized: str) -> str | None:
    for field, candidates in _VOCAB.items():
        if normalized in candidates:
            return field
    return None


def _fuzzy_match(normalized: str) -> tuple[str | None, int]:
    best_field: str | None = None
    best_ratio = 0.0
    for field, candidates in _VOCAB.items():
        for cand in candidates:
            r = SequenceMatcher(None, normalized, cand).ratio()
            if r > best_ratio:
                best_ratio = r
                best_field = field
    if best_field is not None and best_ratio >= FUZZY_THRESHOLD:
        return best_field, round(best_ratio * 100)
    return None, round(best_ratio * 100)


def map_columns(columns: list[str], saved: dict[str, str] | None = None) -> list[dict]:
    """确定性三层映射（saved/exact/fuzzy）。返回每个来源列的映射建议。"""
    results: list[dict] = []
    for col in columns:
        norm = normalize(col)
        target = _saved_match(norm, saved)
        tier = "saved"
        confidence = 100
        if target is None:
            target = _exact_match(norm)
            tier = "exact"
            confidence = 100 if target else 0
        if target is None:
            target, confidence = _fuzzy_match(norm)
            tier = "fuzzy"
        if target is None:
            tier = "unmatched"
            confidence = 0
        results.append(
            {
                "source_column": col,
                "target_field": target,
                "confidence": confidence,
                "tier": tier,
                "needs_review": target is None or tier in ("fuzzy", "unmatched"),
            }
        )
    return results


async def map_columns_with_llm(
    columns: list[str], saved: dict[str, str] | None = None
) -> list[dict]:
    """四层映射：前三层确定性，低置信度列路由 LLM（只发表头元数据）。

    LLM 未配置或失败时退化为纯三层结果（不阻塞接入）。
    """
    results = map_columns(columns, saved)
    low = [r for r in results if r["tier"] in ("unmatched",) or r["confidence"] < LLM_MIN_CONFIDENCE * 100]
    if not low:
        return results

    llm_map = await _llm_map_columns([r["source_column"] for r in low])
    by_col = {m["source_column"]: m for m in llm_map or []}
    for r in results:
        if r["tier"] == "unmatched" or r["confidence"] < LLM_MIN_CONFIDENCE * 100:
            hit = by_col.get(r["source_column"])
            if hit and hit.get("target_field"):
                r["target_field"] = hit["target_field"]
                r["confidence"] = hit.get("confidence", 70)
                r["tier"] = "llm"
                r["needs_review"] = True
    return results


async def _llm_map_columns(columns: list[str]) -> list[dict] | None:
    """LLM 语义映射：仅发送列名 + 源字段词汇表（无原始数据）。失败返回 None。"""
    from app.services import llm_reply
    from app.services.metric_registry import SOURCE_FIELDS

    vocab_lines = ["、".join(sf["field"] for sf in SOURCE_FIELDS)]
    system = (
        "你是数据字段映射器。把用户上传表格的列名映射到目标源字段。"
        f"目标源字段只能是：{vocab_lines[0]}。"
        "只输出 JSON 数组：[{\"source_column\": \"...\", \"target_field\": \"...\", \"confidence\": 0-100}]。"
        "无法确定时 target_field 用 null。禁止输出其它文字。"
    )
    user = "用户列名：" + "、".join(columns)
    text = await llm_reply._plain_completion(system, user, max_tokens=300, temperature=0.0)
    if not text:
        return None
    try:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return None
        data = json.loads(text[start : end + 1])
        return [m for m in data if isinstance(m, dict)]
    except (ValueError, TypeError) as exc:
        logger.warning("llm field map parse failed: %s", exc)
        return None
