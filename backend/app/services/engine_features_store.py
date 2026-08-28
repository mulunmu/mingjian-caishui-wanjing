"""从 PG 读取 ETL 预计算的引擎特征"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_fraud_features_batch(enterprise_ids: list[str]) -> dict[str, dict[str, Any]]:
    """返回 enterprise_id -> 与 analyze_enterprise 兼容的结构（来自 PG）。"""
    if not enterprise_ids:
        return {}
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import EnterpriseEngineFeatures

        with Session(get_sync_engine()) as session:
            rows = session.scalars(
                select(EnterpriseEngineFeatures).where(
                    EnterpriseEngineFeatures.enterprise_id.in_(enterprise_ids)
                )
            ).all()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            signals = json.loads(r.fraud_signals or "[]")
            composite = float(r.fraud_composite_score or 0)
            out[r.enterprise_id] = {
                "enterprise_id": r.enterprise_id,
                "composite_score": composite,
                "risk_level": r.fraud_risk_level or "低风险",
                "signals": signals,
                "scbm_mismatch": {"score": float(r.scbm_mismatch_score or 0)},
                "red_invoice": {
                    "score": float(r.red_invoice_score or 0),
                    "invoice_cnt": int(r.invoice_cnt or 0),
                },
                "concentration": {"score": float(r.concentration_score or 0)},
                "sequence": {"gap_ratio": float(r.sequence_gap_ratio or 0)},
                "pyod_score": float(r.pyod_score or 0),
                "confidence": "computed",
                "trace": {
                    "table": "enterprise_engine_features",
                    "field": "fraud_composite_score",
                    "query_id": "Q_fraud_precomputed",
                },
                "_precomputed": True,
            }
        return out
    except Exception as exc:
        logger.debug("load_fraud_features_batch failed: %s", exc)
        return {}


def load_benford_snapshot() -> dict[str, Any] | None:
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import EngineSnapshot

        with Session(get_sync_engine()) as session:
            row = session.scalar(select(EngineSnapshot).where(EngineSnapshot.key == "benford_global"))
        if not row or not row.payload:
            return None
        return json.loads(row.payload)
    except Exception as exc:
        logger.debug("load_benford_snapshot failed: %s", exc)
        return None
