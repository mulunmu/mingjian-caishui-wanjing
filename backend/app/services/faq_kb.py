"""产品 FAQ 与方法论口径问答（静态 KB，无数字、无 LLM 编造）。

FAQ 回答不带数字（value=None），hallucination_guard 平凡通过；
方法论回答从 metric_registry.CANONICAL_METRICS 取权威口径。
"""
from __future__ import annotations

from app.schemas.claim import Claim, ClaimTrace, ClaimValue

# product_faq 收窄：只覆盖导入 / 指标口径 / 报告生成方式。
# 「能分析哪些企业 / 系统能做什么」归 negotiate_scope，禁止 FAQ 抢答。
FAQ_ENTRIES: list[dict] = [
    {
        "id": "data",
        "keywords": [
            "怎么导入数据",
            "数据怎么导入",
            "怎么导入",
            "如何导入",
            "导入数据",
            "上传数据",
            "接入数据",
            "导数据",
            "传数据",
            "数据接入",
            "上传excel",
            "excel上传",
            "接什么数据",
            "支持什么数据",
            "怎么上传数据",
        ],
        "answer": (
            "数据接入支持 Excel 上传、数据库导入、API 三种方式。"
            "系统会做分层字段映射（已保存→精确→模糊→LLM 语义），并统一到指标语义层口径；"
            "你可选择这份数据会话内临时使用或写入库作为分析材料。"
        ),
        "action": {"label": "打开数据接入", "target": "/ingest"},
    },
    {
        "id": "report",
        "keywords": [
            "报告怎么生成",
            "怎么生成报告",
            "如何生成报告",
            "报告如何生成",
            "怎么出报告",
            "如何出报告",
            "报告怎么导出",
            "怎么下载报告",
        ],
        "answer": (
            "报告是本系统最大卖点，可解释/可追问/可行动。"
            "在对话里说「生成报告」产出组合风险报告；个体画像页说「生成个体深度报告」产出个体 PDF。"
        ),
        "action": {"label": "打开报告中心", "target": "/report"},
    },
    {
        "id": "privacy",
        "keywords": ["怎么脱敏", "隐私怎么", "怎么匿名", "怎么保护隐私", "税号会不会泄露", "企业名隐私", "怎么保护企业名"],
        "answer": (
            "系统对公共源数据做不可逆脱敏：企业名/税号只存 MD5 哈希，无明文，"
            "UI 不暴露单一企业真实身份，所有个体输出仅用「企业N」脱敏序号展示。"
        ),
    },
    {
        "id": "method",
        "keywords": [
            "指标怎么算",
            "评分怎么算",
            "指标定义",
            "算法公式",
            "权重怎么算",
            "综合评分怎么算",
            "真实性得分怎么算",
            "口径怎么算",
            "怎么算的",
        ],
        "answer": (
            "报告结论均来自企业经营数据的客观呈现：先看业务指标波动（如开票环比、申报营收同比），"
            "再判断企业经营行为，最后提示涉税与经营风险点。报告不披露模型内部算法与权重，"
            "如需了解某个指标的业务含义，可直接追问指标名称。"
        ),
    },
]


def match_faq(query: str) -> dict | None:
    q = (query or "").lower()
    for entry in FAQ_ENTRIES:
        if any(kw.lower() in q for kw in entry["keywords"]):
            return entry
    return None


def build_faq_claims(query: str) -> tuple[list[Claim], dict]:
    entry = match_faq(query)
    if entry is None:
        return (
            [
                Claim(
                    claim="抱歉，没找到对应说明。你可以问：数据怎么导入、报告怎么生成、指标怎么算；若想知道能分析哪些企业，直接说「我能分析哪些」。",
                    value=None,
                    trace=ClaimTrace(table="faq_kb", field="answer", query_id="Q_faq_fallback"),
                    confidence="inferred",
                )
            ],
            {
                "faq_id": "fallback",
                "actions": [
                    {"label": "打开数据接入", "target": "/ingest"},
                    {"label": "打开报告中心", "target": "/report"},
                ],
            },
        )
    claim = Claim(
        claim=entry["answer"],
        value=None,
        trace=ClaimTrace(table="faq_kb", field="answer", query_id="Q_faq"),
        confidence="inferred",
        evidence_chain=[f"faq_id={entry['id']}"],
    )
    meta = {"faq_id": entry["id"]}
    if entry.get("action"):
        meta["actions"] = [entry["action"]]
    return [claim], meta


def build_methodology_claims(metrics: list[str] | None = None) -> tuple[list[Claim], dict]:
    from app.services.metric_registry import CANONICAL_METRICS

    requested = metrics or []
    if requested:
        by_key = {m["metric_key"]: m for m in CANONICAL_METRICS}
        selected = [by_key[m] for m in requested if m in by_key]
    else:
        selected = CANONICAL_METRICS

    claims: list[Claim] = []
    for m in selected:
        formula = (m.get("formula") or "").strip()
        edge = (m.get("edge_cases") or "").strip()
        text = f"{m['name']}（{m['metric_key']}）：{m['description']}"
        if formula:
            text += f" 公式：{formula}。"
        if edge:
            text += f" 边界：{edge}"
        claims.append(
            Claim(
                claim=text,
                value=None,
                trace=ClaimTrace(
                    table="metric_definition", field=m["metric_key"], query_id="Q_methodology"
                ),
                confidence="inferred",
                evidence_chain=[f"unit={m.get('unit') or ''}", f"grain={m.get('grain') or ''}"],
            )
        )
    if not claims:
        claims = [
            Claim(
                claim="未找到该指标的口径定义。",
                value=None,
                trace=ClaimTrace(table="metric_definition", field="unknown", query_id="Q_methodology_empty"),
                confidence="inferred",
            )
        ]
    return claims, {"metric_keys": [m["metric_key"] for m in selected]}
