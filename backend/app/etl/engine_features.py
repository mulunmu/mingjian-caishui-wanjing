"""
ETL 步骤：预计算 enterprise_engine_features + Benford 快照

在 pipeline.run() 末尾调用（离线 MySQL 查询可接受）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.urls import get_sync_engine
from app.models.core_metrics import CoreMetrics
from app.models.engine_store import EngineSnapshot, EnterpriseEngineFeatures
from app.services import authenticity_engine, fraud_engine

logger = logging.getLogger(__name__)


def build_engine_features(
    enterprise_ids: list[str] | None = None,
    *,
    max_fraud: int | None = None,
) -> tuple[list[EnterpriseEngineFeatures], EngineSnapshot]:
    """为每个 enterprise_id 计算 fraud + authenticity（同步 MySQL 仅在 ETL）。"""
    engine = get_sync_engine()
    now = datetime.now(timezone.utc)
    features: list[EnterpriseEngineFeatures] = []

    with Session(engine) as session:
        q = select(CoreMetrics)
        if enterprise_ids:
            q = q.where(CoreMetrics.enterprise_id.in_(enterprise_ids))
        metrics = list(session.scalars(q).all())

    if max_fraud is not None:
        metrics = metrics[: max_fraud]

    fraud_rows: list[tuple[str, dict]] = []
    pyod_matrix: list[list[float]] = []

    for m in metrics:
        auth = authenticity_engine.analyze_authenticity_from_metrics(m)
        fraud = None
        try:
            fraud = fraud_engine.analyze_enterprise(m.enterprise_id)
        except Exception as exc:
            logger.debug("ETL fraud skip %s: %s", m.enterprise_id, exc)

        if fraud:
            fraud_rows.append((m.enterprise_id, fraud))
            pyod_matrix.append(
                [
                    fraud["scbm_mismatch"]["score"],
                    fraud["red_invoice"]["score"],
                    fraud["concentration"]["score"],
                    fraud["sequence"]["gap_ratio"] * 100,
                ]
            )
        else:
            pyod_matrix.append([0.0, 0.0, 0.0, 0.0])

    anomaly = fraud_engine.pyod_anomaly_scores(np.array(pyod_matrix)) if pyod_matrix else np.array([])
    fraud_by_id = {eid: fr for eid, fr in fraud_rows}

    for i, m in enumerate(metrics):
        fr = fraud_by_id.get(m.enterprise_id)
        auth = authenticity_engine.analyze_authenticity_from_metrics(m)
        pyod = round(float(anomaly[i]) * 100, 2) if i < len(anomaly) else 0.0
        signals = fr["signals"] if fr else []
        features.append(
            EnterpriseEngineFeatures(
                enterprise_id=m.enterprise_id,
                # analyze_enterprise 返回 composite_score / risk_level
                fraud_composite_score=(fr.get("composite_score") if fr else 0) or 0,
                fraud_risk_level=(fr.get("risk_level") if fr else None) or "低风险",
                fraud_signals=json.dumps(signals, ensure_ascii=False),
                scbm_mismatch_score=(fr or {}).get("scbm_mismatch", {}).get("score", 0) or 0,
                red_invoice_score=(fr or {}).get("red_invoice", {}).get("score", 0) or 0,
                concentration_score=(fr or {}).get("concentration", {}).get("score", 0) or 0,
                sequence_gap_ratio=(fr or {}).get("sequence", {}).get("gap_ratio", 0) or 0,
                pyod_score=pyod,
                authenticity_score=auth.get("authenticity_score") or 0,
                cross_avg_deviation=(auth.get("cross_source") or {}).get("avg_deviation"),
                cross_suspicious=bool((auth.get("cross_source") or {}).get("suspicious")),
                invoice_cnt=(fr or {}).get("red_invoice", {}).get("invoice_cnt")
                or int(getattr(m, "invoice_cnt", 0) or 0),
                updated_at=now,
            )
        )

    # Benford 全局快照（一次 MySQL 抽样）
    amounts = authenticity_engine.load_finance_amounts_for_benford()
    if len(amounts) < 50:
        amounts = [
            float(getattr(m, "finance_revenue", 0) or getattr(m, "vat_revenue", 0) or getattr(m, "invoice_revenue", 0))
            for m in metrics
        ]
        amounts = [a for a in amounts if abs(a) >= 1]
    benford = authenticity_engine.benford_test(amounts, min_n=30)
    snap = EngineSnapshot(
        key="benford_global",
        payload=json.dumps(benford, ensure_ascii=False, default=str),
        updated_at=now,
    )
    logger.info("Built %d engine features, benford n=%s", len(features), benford.get("n"))
    return features, snap


def write_engine_features(
    features: list[EnterpriseEngineFeatures],
    snapshot: EngineSnapshot,
) -> None:
    from app.db.session import Base
    import app.models  # noqa: F401 — 确保 metadata 含 engine 表

    engine = get_sync_engine()
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as session:
        session.query(EnterpriseEngineFeatures).delete()
        session.query(EngineSnapshot).filter(EngineSnapshot.key == snapshot.key).delete()
        session.bulk_save_objects(features)
        session.add(snapshot)
        session.commit()
    logger.info("Wrote %d enterprise_engine_features + snapshot %s", len(features), snapshot.key)


if __name__ == "__main__":
    import argparse
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Rebuild enterprise_engine_features + Benford snapshot")
    ap.add_argument("--max", type=int, default=None, help="最多处理 N 家（调试）")
    ns = ap.parse_args()
    feats, snap = build_engine_features(max_fraud=ns.max)
    write_engine_features(feats, snap)
    print(f"OK features={len(feats)} benford_key={snap.key}")
