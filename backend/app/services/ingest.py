"""行级数据 ETL（阶段二 · 数据接入最后一块）。

把「已确认映射 + 行数据」落地为 core_metrics 行。铁律：
- 身份（税号/企业名/统一编号）只做 MD5，明文永不落库、永不回显；
- display_label 只存「地区·行业·规模」匿名标签（对齐 mock_data._anon_display_label）；
- 数值只剥离分隔符，不做 %/万/亿 隐式换算——口径归用户负责，语义层只文档化（防口径漂移）。
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.enterprise_id import enterprise_id_of

logger = logging.getLogger(__name__)

# 目标字段 → 类型（与 core_metrics 列对齐）。不在表内视为 str。
FIELD_TYPES: dict[str, str] = {
    "industry_l1": "str",
    "industry_l2": "str",
    "province": "str",
    "city": "str",
    "scale_label": "str",
    "credit_level": "str",
    "credit_score": "decimal",
    "tax_on_time_rate": "decimal",
    "tax_arrears_cnt": "int",
    "tax_violation_cnt": "int",
    "high_severity_cnt": "int",
    "tax_late_penalty_cnt": "int",
    "correction_times": "int",
    "vat_burden": "decimal",
    "is_dishonesty": "bool",
    "is_execution": "bool",
    "loan_cnt": "int",
    "loan_amount": "decimal",
    "vat_revenue": "decimal",
    "invoice_revenue": "decimal",
    "finance_revenue": "decimal",
    "revenue_deviation": "decimal",
    "invoice_monthly_avg": "int",
    "invoice_cnt": "int",
    "red_invoice_cnt": "int",
    "void_invoice_cnt": "int",
    "customer_concentration": "decimal",
    "supplier_concentration": "decimal",
    "category_concentration": "decimal",
    "unit_price_ratio": "decimal",
    "social_trend": "str",
    "social_months": "int",
    "profit_margin": "decimal",
    "revenue_yoy": "decimal",
    "profit_yoy": "decimal",
    "debt_ratio": "decimal",
    "cash_flow_net": "decimal",
    "cash_flow_level": "str",
    "current_ratio": "decimal",
    "quick_ratio": "decimal",
    "gross_margin": "decimal",
    "net_margin": "decimal",
    "roe": "decimal",
    "roa": "decimal",
    "receivables_turnover": "decimal",
    "inventory_turnover": "decimal",
    "asset_turnover": "decimal",
    "has_financial_statements": "bool",
}

# core_metrics 非空且无默认值的字符串列，缺省兜底（避免 NOT NULL 失败）。
STRING_DEFAULTS: dict[str, str] = {
    "industry_l2": "",
    "city": "",
    "credit_level": "暂无",
    "scale_label": "小微",
    "social_trend": "稳定",
    "cash_flow_level": "一般",
}

_TRUE = {"是", "true", "1", "yes", "y", "真", "有", "1.0"}
_FALSE = {"否", "false", "0", "no", "n", "假", "无", "0.0", ""}


def _clean_num(s: str) -> str:
    for ch in ",，%¥￥  ":
        s = s.replace(ch, "")
    return s.strip()


def coerce_value(field: str, raw: Any) -> tuple[Any, str | None]:
    """返回 (value, error)；value=None 且无 error 表示跳过（留默认）。"""
    if raw is None:
        return None, None
    ftype = FIELD_TYPES.get(field, "str")

    if ftype == "str":
        return str(raw).strip(), None

    if ftype == "int":
        if isinstance(raw, bool):
            return None, f"{field} 布尔值不能作整数: {raw!r}"
        if isinstance(raw, int):
            return raw, None
        try:
            return int(float(_clean_num(str(raw)))), None
        except (ValueError, TypeError):
            return None, f"{field} 非整数: {raw!r}"

    if ftype == "decimal":
        if isinstance(raw, bool):
            return None, f"{field} 布尔值不能作数值: {raw!r}"
        if isinstance(raw, (int, float, Decimal)):
            return Decimal(str(raw)), None
        try:
            return Decimal(_clean_num(str(raw))), None
        except (InvalidOperation, ValueError):
            return None, f"{field} 非数值: {raw!r}"

    if ftype == "bool":
        if isinstance(raw, bool):
            return raw, None
        s = str(raw).strip().lower()
        if s in _TRUE:
            return True, None
        if s in _FALSE:
            return False, None
        return None, f"{field} 非布尔: {raw!r}"

    return str(raw).strip(), None


def derive_display_label(province: str | None, industry_l1: str | None, scale_label: str | None, revenue: Any) -> str:
    """匿名标签「地区·行业·规模」，与 mock_data._anon_display_label 同构。"""
    prov = province or "未知"
    l1 = industry_l1 or "其他"
    scale = scale_label or "小微"
    if not scale_label:  # 用户未显式给规模时，按营收推导
        try:
            rev = float(revenue or 0)
        except (TypeError, ValueError):
            rev = 0.0
        if rev >= 3_000_000_000:
            scale = "中型"
        elif rev >= 500_000_000:
            scale = "小型"
        else:
            scale = "小微"
    return f"{prov}·{l1}·{scale}"


def process_ingest_rows(
    rows: list[dict],
    mappings: dict[str, str],
    identity_field: str | None,
) -> tuple[list[dict], list[dict]]:
    """纯函数：映射 + 强转 + 派生身份/匿名标签。

    返回 (ingested, errors)。ingested 每项：{enterprise_id, display_label, fields: dict[target_field, value]}。
    errors 每项：{index, source, error}。
    """
    ingested: list[dict] = []
    errors: list[dict] = []

    for idx, raw in enumerate(rows):
        if not isinstance(raw, dict):
            errors.append({"index": idx, "error": "行必须是对象"})
            continue

        # 1) 身份：唯一键 → MD5 enterprise_id（明文不落库）
        if not identity_field:
            errors.append({"index": idx, "error": "未指定身份字段（税号/企业名/统一编号）"})
            continue
        identity_value = raw.get(identity_field)
        if identity_value in (None, ""):
            errors.append({"index": idx, "source": identity_field, "error": "身份字段为空"})
            continue
        enterprise_id = enterprise_id_of(str(identity_value))

        # 2) 字段映射 + 强转
        fields: dict[str, Any] = {}
        row_errors: list[str] = []
        for src, tgt in mappings.items():
            if not tgt:
                continue
            val, err = coerce_value(tgt, raw.get(src))
            if err:
                row_errors.append(err)
            elif val is not None:
                fields[tgt] = val

        # 3) 匿名标签
        province = fields.get("province") or STRING_DEFAULTS.get("province", "")
        l1 = fields.get("industry_l1") or "其他"
        scale = fields.get("scale_label")
        revenue = fields.get("vat_revenue") or fields.get("invoice_revenue")
        display_label = derive_display_label(province, l1, scale, revenue)

        if row_errors:
            errors.append({"index": idx, "source": str(identity_value)[:8], "error": "；".join(row_errors)})
        ingested.append(
            {"enterprise_id": enterprise_id, "display_label": display_label, "fields": fields}
        )

    return ingested, errors


def to_core_metrics_kwargs(item: dict) -> dict:
    """把 ingested 项展开为 core_metrics 构造参数（含非空字符串兜底）。"""
    kwargs: dict[str, Any] = {
        "enterprise_id": item["enterprise_id"],
        "display_label": item["display_label"],
    }
    fields = item["fields"]
    # 必填字符串兜底
    kwargs["industry_l1"] = fields.get("industry_l1") or "其他"
    kwargs["industry_l2"] = fields.get("industry_l2") or STRING_DEFAULTS["industry_l2"]
    kwargs["province"] = fields.get("province") or "未知"
    kwargs["city"] = fields.get("city") or STRING_DEFAULTS["city"]
    # 其余字段原样写入（有默认值的列可省略）
    for k, v in fields.items():
        kwargs.setdefault(k, v)
    return kwargs
