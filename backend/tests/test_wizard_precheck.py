"""向导预校验契约：空范围拦截；有样本可通过。"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.services import slice_report


@pytest.mark.asyncio
async def test_validate_wizard_enterprise_missing(monkeypatch):
    async def fake_cache(db):
        return []

    monkeypatch.setattr(slice_report.assessment, "_ensure_cache", fake_cache)
    out = await slice_report.validate_wizard_report(None, enterprise_id="nope")
    assert out["ok"] is False
    assert "未找到" in out["reason"]


@pytest.mark.asyncio
async def test_validate_wizard_enterprise_found(monkeypatch):
    async def fake_cache(db):
        return [
            SimpleNamespace(
                enterprise_id="e1",
                display_name="企业甲",
                display_label="企业甲",
                industry_l1="制造",
                province="广东",
            )
        ]

    monkeypatch.setattr(slice_report.assessment, "_ensure_cache", fake_cache)
    out = await slice_report.validate_wizard_report(None, enterprise_id="e1")
    assert out["ok"] is True
    assert out["mode"] == "enterprise"


@pytest.mark.asyncio
async def test_validate_wizard_slice_empty_scope(monkeypatch):
    async def fake_validate_custom(db, **kwargs):
        return {"chapters": {"financial": {"available": False, "sample_count": 0}}, "scope_sample_count": 0}

    async def fake_block(db, **kwargs):
        return "「制造」筛选下没有匹配样本。"

    monkeypatch.setattr(slice_report, "validate_custom_report", fake_validate_custom)
    monkeypatch.setattr(slice_report, "custom_report_block_reason", fake_block)
    monkeypatch.setattr(slice_report, "is_premium_locked", lambda: False)
    out = await slice_report.validate_wizard_report(None, scenario="financial", industry_l1="制造")
    assert out["ok"] is False
    assert out["scope_sample_count"] == 0
    assert out["reason"]


@pytest.mark.asyncio
async def test_validate_wizard_slice_ok(monkeypatch):
    async def fake_validate_custom(db, **kwargs):
        return {
            "chapters": {
                "financial": {"available": True, "sample_count": 10},
                "authenticity": {"available": True, "sample_count": 10},
            },
            "scope_sample_count": 60,
        }

    monkeypatch.setattr(slice_report, "validate_custom_report", fake_validate_custom)
    monkeypatch.setattr(slice_report, "is_premium_locked", lambda: False)
    out = await slice_report.validate_wizard_report(None, scenario="financial")
    assert out["ok"] is True
    assert out["available_chapter_count"] == 2
    assert out["scope_sample_count"] == 60
