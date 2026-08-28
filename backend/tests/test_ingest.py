"""行级数据 ETL（阶段二）"""
import os
import re
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ingest import (
    coerce_value,
    derive_display_label,
    process_ingest_rows,
    to_core_metrics_kwargs,
)

_ID_HEX = re.compile(r"^[0-9a-f]{32}$")


def test_coerce_value_types():
    assert coerce_value("credit_score", "92.5")[0] == Decimal("92.5")
    assert coerce_value("tax_arrears_cnt", "3")[0] == 3
    assert coerce_value("is_dishonesty", "是")[0] is True
    assert coerce_value("industry_l1", "制造")[0] == "制造"
    # 非法数值 → 返回 None + 错误
    v, err = coerce_value("credit_score", "abc")
    assert v is None and err


def test_coerce_value_strips_separators():
    assert coerce_value("vat_revenue", "1,234,567.89")[0] == Decimal("1234567.89")


def test_derive_display_label_anonymous():
    assert derive_display_label("浙江", "制造", None, Decimal("6000000000")) == "浙江·制造·中型"
    assert derive_display_label(None, None, "小微", None) == "未知·其他·小微"


def test_process_ingest_rows_hashes_identity():
    identity = "91330100MA0000000X"
    mappings = {"税号": None, "信用分": "credit_score", "省份": "province", "行业大类": "industry_l1"}
    rows = [{"税号": identity, "信用分": "92.5", "省份": "浙江", "行业大类": "制造"}]
    ingested, errors = process_ingest_rows(rows, mappings, identity_field="税号")

    assert len(ingested) == 1
    eid = ingested[0]["enterprise_id"]
    assert _ID_HEX.fullmatch(eid), "enterprise_id 必须是 32 位 MD5"
    assert eid != identity
    # 明文身份永不落进结果
    assert identity not in str(ingested)
    assert ingested[0]["fields"]["credit_score"] == Decimal("92.5")
    assert ingested[0]["display_label"] == "浙江·制造·小微"


def test_process_ingest_rows_identity_missing():
    mappings = {"信用分": "credit_score"}
    rows = [{"信用分": "90"}]
    ingested, errors = process_ingest_rows(rows, mappings, identity_field="税号")
    assert len(ingested) == 0
    assert any("身份字段为空" in e["error"] for e in errors)


def test_process_ingest_rows_invalid_numeric_reported():
    mappings = {"税号": None, "信用分": "credit_score"}
    rows = [{"税号": "91330100MA0000000Y", "信用分": "不是数字"}]
    ingested, errors = process_ingest_rows(rows, mappings, identity_field="税号")
    assert len(ingested) == 1  # 仍入列，但数值字段被跳过
    assert "credit_score" not in ingested[0]["fields"]
    assert any("credit_score" in e["error"] for e in errors)


def test_to_core_metrics_kwargs_fills_required_strings():
    item = {
        "enterprise_id": "a" * 32,
        "display_label": "未知·其他·小微",
        "fields": {"credit_score": Decimal("90")},
    }
    kw = to_core_metrics_kwargs(item)
    assert kw["enterprise_id"] == "a" * 32
    assert kw["industry_l1"] == "其他"
    assert kw["province"] == "未知"
    assert kw["city"] == ""
    assert kw["credit_score"] == Decimal("90")
