"""Chat 路由 mock / 模板回退"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_template_reply_all_intents():
    from app.services.llm_reply import _template_reply

    intents = [
        "score_overall",
        "authenticity_overall",
        "benchmark_industry",
        "trend_industry",
        "signal_signal",
        "report_overall",
        "email_report_overall",
        "general",
    ]
    for intent in intents:
        reply = _template_reply(intent, {}, with_prefix=True)
        assert len(reply) > 0


def test_template_reply_with_claims():
    from app.services.llm_reply import _template_reply

    data = {
        "claims": [
            {
                "claim": "制造行业营收同比均值 3.5%。",
                "value": {"metric": "avg_revenue_yoy", "number": 3.5, "unit": "%"},
                "confidence": "computed",
            }
        ],
        "followups": ["看真实性"],
    }
    reply = _template_reply("trend_industry", data, with_prefix=True)
    assert "3.5" in reply
    assert "下方按钮可继续追问" in reply
