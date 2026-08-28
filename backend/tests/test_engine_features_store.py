"""PG 预计算引擎特征读取"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.engine_features_store import load_benford_snapshot, load_fraud_features_batch


def test_load_fraud_features_empty():
    assert load_fraud_features_batch([]) == {}


def test_load_benford_snapshot_optional():
    snap = load_benford_snapshot()
    assert snap is None or isinstance(snap, dict)
