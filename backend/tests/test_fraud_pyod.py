"""PyOD 异常分方向：离群点应高于正常点"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_pyod_anomaly_scores_outlier_higher_than_normal():
    from app.services.fraud_engine import pyod_anomaly_scores

    rng = np.random.RandomState(42)
    normal = rng.rand(24, 4) * 8 + 40
    outlier = np.array([[200.0, 200.0, 200.0, 200.0]])
    scores = pyod_anomaly_scores(np.vstack([normal, outlier]))
    assert len(scores) == 25
    assert float(scores[-1]) > float(np.median(scores[:-1]))
