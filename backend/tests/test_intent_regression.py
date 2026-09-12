"""意图识别核心业务回归样例（扩展版 200+ 条）—— 规则引擎识别准确率须 100%。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.intent_regression import evaluate_regression, REGRESSION_CASES


def test_regression_suite_has_200_plus():
    assert len(REGRESSION_CASES) >= 200, f"回归样例 {len(REGRESSION_CASES)} 条，不足 200 条"


def test_regression_accuracy_100():
    r = evaluate_regression()
    assert r["accuracy"] == 100.0, (
        f"识别准确率 {r['accuracy']}%（{r['correct']}/{r['total']}），未全命中：{r['failures']}"
    )
