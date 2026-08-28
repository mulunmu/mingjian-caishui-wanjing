"""ETL 小工具函数（report_year 抽取，弃权优先）"""
import sys
import os
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.etl.pipeline import _report_year


def test_report_year_from_date():
    assert _report_year(date(2024, 12, 31)) == "2024"


def test_report_year_from_datetime():
    assert _report_year(datetime(2025, 6, 30, 10, 0, 0)) == "2025"


def test_report_year_from_string():
    assert _report_year("2023-12-31") == "2023"


def test_report_year_abstain():
    # 缺失/不可解析 → None（弃权，不编造年份）
    assert _report_year(None) is None
    assert _report_year("") is None
    assert _report_year("abc") is None
    assert _report_year("20") is None
