"""差异驱动异动检测：从洞察 + 同比变动 + 新增税务/司法事件，产出可推送的异动信号。

铁律（与《报告设计规范 v1》一致）：
- 数字只来自 L0 计算层（CoreMetrics / EnterpriseFinancials / LegalEvent）；
- 弃权优先于编造：同比 0=弃权（无数据）时不产「较上期恶化」信号；
- 客观评级复用 insight_engine 确定性规则，不另设黑盒阈值；
- 每条信号 traceable 到源表字段。

异动标签（同一批数据 → 同一标签，与场景/立场无关）：
- 高危 / 预警：来自洞察引擎的客观评级；
- 较上期恶化：同比驱动的经营拐点（营收下滑、增收不增利、ROE 转负、现金流净流出）；
- 新增：本次数据刷新纳入的税务违法/稽查事件。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.core_metrics import CoreMetrics, LegalEvent
from app.models.financials import EnterpriseFinancials
from app.services.insight_engine import Insight

# 洞察规则 → 异动标签（较上期恶化 = 同比/趋势性拐点，属「差异驱动」而非静态风险）
_CHANGE_RULES = {
    "F-02": "较上期恶化",  # 经营现金流净流出
    "F-03": "较上期恶化",  # 增收不增利
    "F-04": "较上期恶化",  # 营收显著下滑
    "F-09": "较上期恶化",  # 净资产收益率为负
}

# 新增事件的回溯窗口（天）：event_date 在此窗口内视为「新发生」
RECENT_WINDOW_DAYS = 180

TAG_ORDER = {"高危": 0, "新增": 1, "较上期恶化": 2, "预警": 3}
LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2}

_EVENT_TYPE_LABEL = {
    "tax_violation": "税务违法",
    "tax_audit": "税务稽查",
}


def _f(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _signal(
    signal_id: str,
    tag: str,
    category: str,
    title: str,
    level: str,
    evidence: str,
    advice: str,
    *,
    table: str,
    field: str,
) -> dict[str, Any]:
    return {
        "signal_id": signal_id,
        "tag": tag,
        "category": category,
        "title": title,
        "level": level,
        "evidence": evidence,
        "advice": advice,
        "trace": {"table": table, "field": field},
    }


def _insight_signals(insights: list[Insight]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ins in insights:
        tag = _CHANGE_RULES.get(ins.rule_id, ins.severity)
        level = "high" if ins.severity == "高危" else "medium"
        out.append(
            _signal(
                ins.rule_id,
                tag,
                ins.category,
                ins.title,
                level,
                ins.fact_text(),
                ins.advice,
                table=(ins.primary.table if ins.primary else "core_metrics"),
                field=(ins.primary.field if ins.primary else ins.rule_id),
            )
        )
    return out


def _legal_signals(
    legal_events: list[LegalEvent], *, days: int = RECENT_WINDOW_DAYS
) -> list[dict[str, Any]]:
    """新增税务/司法事件：仅回溯窗口内（或时效未知）的事件标「新增」。

    - event_date 在窗口内 → 新增（确有近期事件）；
    - event_date 缺失 → 新增（本次刷新纳入，时效未知，保守标注）；
    - event_date 超出窗口 → 历史事件，已由聚合洞察覆盖，跳过（弃权，不冒称「新增」）。
    """
    out: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for ev in legal_events:
        etype = ev.event_type or "tax_violation"
        label = _EVENT_TYPE_LABEL.get(etype, etype)
        sev = (ev.severity or "M").upper()
        level = "high" if sev == "H" else "medium"
        when = ""
        if ev.event_date is not None:
            ed = ev.event_date
            if ed.tzinfo is None:
                ed = ed.replace(tzinfo=timezone.utc)
            if ed < cutoff:
                # 超出回溯窗口的历史事件：非「新增」，跳过（由 T-01/T-02 聚合洞察覆盖）
                continue
            when = f"（{ed.strftime('%Y-%m-%d')}）"
        else:
            when = "（时效未知）"
        out.append(
            _signal(
                f"LEGAL-{ev.id or label}",
                "新增",
                "税务" if etype.startswith("tax_") else "司法",
                f"新增{label}事件",
                level,
                f"{label}{when}",
                "新增税务/司法事件，建议调取事件详情核查其影响。",
                table="legal_events",
                field="event_type",
            )
        )
    return out


def detect_anomalies(
    metrics: CoreMetrics | None,
    financials: EnterpriseFinancials | None,
    insights: list[Insight],
    legal_events: list[LegalEvent] | None = None,
) -> list[dict[str, Any]]:
    """组装异动信号并排序（高危 > 新增 > 较上期恶化 > 预警）。

    metrics/financials 为 None 时仅能从洞察与事件层产出，弃权不编造同比信号。
    """
    signals: list[dict[str, Any]] = []
    signals.extend(_insight_signals(insights))
    signals.extend(_legal_signals(legal_events or []))

    signals.sort(
        key=lambda s: (
            LEVEL_ORDER.get(s["level"], 9),
            TAG_ORDER.get(s["tag"], 9),
            s["signal_id"],
        )
    )
    return signals


def has_material_anomaly(signals: list[dict[str, Any]], *, threshold: int = 1) -> bool:
    """是否存在值得推送的实质异动：任一高危信号，或异动信号数达阈值。"""
    if any(s["level"] == "high" for s in signals):
        return True
    return len(signals) >= threshold
