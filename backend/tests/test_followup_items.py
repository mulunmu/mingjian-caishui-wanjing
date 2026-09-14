"""刀 1：结构化 followup / 下钻 / FAQ 去闭环。"""
from __future__ import annotations

from app.services import followup_items as fu


def test_faq_followups_no_loop():
    items = fu.build_faq_followups()
    labels = " ".join(fu.labels_of(items))
    assert "这个系统能做什么" not in labels
    assert "数据怎么导入" not in labels
    assert "报告怎么生成" not in labels
    assert any(x["type"] == "navigate" and x.get("target") == "ingest" for x in items)
    assert any(x["type"] == "navigate" and x.get("target") == "report_generate" for x in items)


def test_normalize_strips_appendix_word():
    items = fu.normalize_legacy_strings(["下载后核对附录数据说明", "生成报告"])
    assert all("附录" not in (x.get("label") or "") for x in items)
    assert any(x["type"] == "navigate" and x.get("target") == "report_generate" for x in items)


def test_fraud_followups_have_three_kinds():
    items = fu.build_fraud_followups({"flagged_count": 62, "signal_counts": {"scbm_mismatch": 40}})
    types = {x["type"] for x in items}
    assert "drilldown" in types
    assert "action" in types
    assert "navigate" in types
    assert any(x.get("op") == "group_by_industry" for x in items)
    # 动作句不应被当成 query
    assert not any(x["type"] == "query" and str(x["label"]).startswith("调这") for x in items)


def test_enrich_faq_meta():
    items = fu.enrich_followups_for_meta(
        ["这个系统能做什么", "数据怎么导入", "报告怎么生成"],
        {"query_type": "faq", "function": "faq"},
    )
    labels = fu.labels_of(items)
    assert "这个系统能做什么" not in labels


def test_group_by_industry_drilldown_sync():
    """纯函数路径：有名单时按行业聚合（不打库）。"""
    import asyncio

    session = {
        "active_conclusion": {
            "claim_id": "c_fraud_flagged",
            "meta": {
                "flagged_count": 3,
                "flagged_firms": [
                    {"enterprise_id": "a", "display_name": "企业1", "industry_l1": "制造", "signals": []},
                    {"enterprise_id": "b", "display_name": "企业2", "industry_l1": "制造", "signals": []},
                    {"enterprise_id": "c", "display_name": "企业3", "industry_l1": "批发零售", "signals": []},
                ],
            },
        }
    }

    async def _run():
        return await fu.run_drilldown(
            None,
            op="group_by_industry",
            claim_id="c_fraud_flagged",
            params={},
            session_context=session,
        )

    out = asyncio.run(_run())
    assert out["ok"] is True
    assert out["meta"].get("charts", {}).get("type") == "bar"
    claim_text = out["claims"][0].claim
    assert "制造" in claim_text or "2" in claim_text
