"""
反欺诈引擎 — 确定性算法产出信号与异常分

信号：
1. 进销商品错配（scbm 前缀 Jaccard 距离）
2. 红字发票异常占比
3. 开票集中度（Top1 金额占比）
4. 发票号码序列错配（参考 acc_fraud_detections）
5. pyod IsolationForest 综合异常分
"""
from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    from pyod.models.iforest import IForest
    _HAS_PYOD = True
except Exception:  # pragma: no cover
    _HAS_PYOD = False


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def detect_sequence_mismatches(
    invoice_numbers: list[str | int],
    *,
    max_local_missing: int = 20,
) -> dict[str, Any]:
    """
    发票号码「局部跳号」检测。

    注意：同一纳税人 fphm 常跨多个票本/年份，全局 min→max 的缺口占比几乎恒为 ~1，
    不能当作欺诈信号。只统计相邻号码之间「小缺口」(1..max_local_missing) 的频次。
    """
    nums: list[int] = []
    for x in invoice_numbers:
        s = re.sub(r"\D", "", str(x or ""))
        if s.isdigit():
            nums.append(int(s))
    if len(nums) < 2:
        return {
            "gap_count": 0,
            "gap_ratio": 0.0,
            "gaps": [],
            "sample_size": len(nums),
            "pair_count": 0,
            "local_gap_events": 0,
            "batch_jumps": 0,
        }

    nums = sorted(set(nums))
    local_gaps: list[dict] = []
    batch_jumps = 0
    for i in range(1, len(nums)):
        missing = nums[i] - nums[i - 1] - 1
        if missing <= 0:
            continue
        if missing <= max_local_missing:
            local_gaps.append({"from": nums[i - 1], "to": nums[i], "missing": missing})
        else:
            batch_jumps += 1

    pair_count = len(nums) - 1
    local_events = len(local_gaps)
    gap_count = sum(g["missing"] for g in local_gaps)
    # 相邻对中出现局部跳号的比例（而非跨票本全局空洞）
    gap_ratio = local_events / pair_count if pair_count > 0 else 0.0
    return {
        "gap_count": gap_count,
        "gap_ratio": round(gap_ratio, 4),
        "gaps": local_gaps[:20],
        "sample_size": len(nums),
        "pair_count": pair_count,
        "local_gap_events": local_events,
        "batch_jumps": batch_jumps,
        "max_local_missing": max_local_missing,
    }


def scbm_mismatch_score(buy_prefixes: list[str], sell_prefixes: list[str]) -> dict[str, Any]:
    """
    进销商品税控编码前缀错配：
    以「销项类目在进项中找不到」为主信号；Jaccard 仅作 trace 参考。

    贸易企业常「进多销少」，纯 Jaccard 会把大量正常批发零售误报为错配。
    """
    buy = {p[:4] for p in buy_prefixes if p and len(str(p)) >= 4}
    sell = {p[:4] for p in sell_prefixes if p and len(str(p)) >= 4}
    if not buy or not sell:
        return {
            "score": 0.0,
            "jaccard_distance": 0.0,
            "orphan_sell_ratio": 0.0,
            "orphan_sell_classes": 0,
            "buy_classes": len(buy),
            "sell_classes": len(sell),
            "overlap": 0,
            "signal": False,
            "label": "进销样本不足",
        }
    inter = buy & sell
    union = buy | sell
    jaccard = len(inter) / len(union) if union else 1.0
    distance = 1.0 - jaccard
    orphan_sell = sell - buy
    orphan_ratio = len(orphan_sell) / len(sell) if sell else 0.0
    # 销项≥2 类目且半数以上在进项无对应 → 强信号（验收假样本仍命中）
    signal = orphan_ratio >= 0.5 and len(sell) >= 2 and len(buy) >= 2
    score = round(min(100.0, orphan_ratio * 100), 2)
    return {
        "score": score,
        "jaccard_distance": round(distance, 4),
        "orphan_sell_ratio": round(orphan_ratio, 4),
        "orphan_sell_classes": len(orphan_sell),
        "buy_classes": len(buy),
        "sell_classes": len(sell),
        "overlap": len(inter),
        "signal": signal,
        "label": "进销商品错配" if signal else "进销品类基本匹配",
    }


def red_invoice_anomaly(red_cnt: int, invoice_cnt: int, industry_avg_ratio: float = 0.02) -> dict[str, Any]:
    ratio = (red_cnt / invoice_cnt) if invoice_cnt > 0 else 0.0
    # 相对行业均值的倍数
    lift = ratio / industry_avg_ratio if industry_avg_ratio > 0 else 0.0
    signal = ratio >= 0.08 or lift >= 3.0
    score = round(min(100.0, ratio * 400 + max(0, lift - 1) * 15), 2)
    return {
        "score": score,
        "red_cnt": red_cnt,
        "invoice_cnt": invoice_cnt,
        "red_ratio": round(ratio, 4),
        "industry_avg_ratio": industry_avg_ratio,
        "lift": round(lift, 2),
        "signal": signal,
        "label": "红字发票异常" if signal else "红字发票占比正常",
    }


def concentration_score(amounts: list[float], top_n: int = 1) -> dict[str, Any]:
    """开票金额集中度：Top1 / 合计。"""
    vals = [abs(a) for a in amounts if a is not None and abs(_f(a)) > 0]
    if not vals:
        return {"score": 0.0, "top_ratio": 0.0, "hhi": 0.0, "signal": False, "label": "无金额样本"}
    total = sum(vals)
    vals_sorted = sorted(vals, reverse=True)
    top_ratio = sum(vals_sorted[:top_n]) / total if total else 0.0
    shares = [v / total for v in vals]
    hhi = sum(s * s for s in shares)
    signal = top_ratio >= 0.6 or hhi >= 0.35
    score = round(min(100.0, top_ratio * 80 + hhi * 40), 2)
    return {
        "score": score,
        "top_ratio": round(top_ratio, 4),
        "hhi": round(hhi, 4),
        "counterparties": len(vals),
        "signal": signal,
        "label": "开票集中度偏高" if signal else "开票集中度正常",
    }


def pyod_anomaly_scores(feature_matrix: np.ndarray) -> np.ndarray:
    """IsolationForest 异常分（0-1，越高越异常）。样本过少时回退到 z-score。"""
    X = np.asarray(feature_matrix, dtype=float)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    n = X.shape[0]
    if n < 5 or not _HAS_PYOD:
        # z-score 均值绝对偏差归一
        mu = X.mean(axis=0)
        sd = X.std(axis=0) + 1e-6
        z = np.abs((X - mu) / sd).mean(axis=1)
        return np.clip(z / (z.max() + 1e-6), 0, 1) if n else np.array([])

    clf = IForest(contamination=0.1, random_state=42, n_estimators=100)
    clf.fit(X)
    # pyod IForest：decision_function 越高越异常（与 sklearn 约定相反）
    df = clf.decision_function(X)
    mn, mx = float(df.min()), float(df.max())
    if mx - mn < 1e-9:
        return np.zeros(n)
    return (df - mn) / (mx - mn)


def analyze_invoice_bundle(
    *,
    buy_scbm: list[str],
    sell_scbm: list[str],
    red_cnt: int,
    invoice_cnt: int,
    amounts_by_counterparty: list[float],
    invoice_numbers: list[str | int] | None = None,
    industry_red_ratio: float = 0.02,
) -> dict[str, Any]:
    """对单一样本（企业或伪造样本）输出完整反欺诈结论。"""
    mismatch = scbm_mismatch_score(buy_scbm, sell_scbm)
    red = red_invoice_anomaly(red_cnt, invoice_cnt, industry_red_ratio)
    conc = concentration_score(amounts_by_counterparty)
    seq = detect_sequence_mismatches(invoice_numbers or [])

    signals = []
    if mismatch["signal"]:
        signals.append("scbm_mismatch")
    if red["signal"]:
        signals.append("red_invoice")
    if conc["signal"]:
        signals.append("concentration")
    if seq["gap_ratio"] >= 0.12 and seq.get("local_gap_events", 0) >= 8 and seq["sample_size"] >= 30:
        signals.append("sequence_gap")

    # 综合分：加权
    composite = (
        mismatch["score"] * 0.35
        + red["score"] * 0.25
        + conc["score"] * 0.25
        + min(100.0, seq["gap_ratio"] * 200) * 0.15
    )
    return {
        "composite_score": round(composite, 2),
        "risk_level": _risk(composite),
        "signals": signals,
        "scbm_mismatch": mismatch,
        "red_invoice": red,
        "concentration": conc,
        "sequence": seq,
        "confidence": "computed",
        "trace": {
            "tables": ["syx_invoice", "syx_invoice_details", "syx_red_invoices_info"],
            "methods": ["scbm_jaccard", "red_ratio", "hhi", "sequence_gap", "iforest"],
        },
    }


def _risk(score: float) -> str:
    if score >= 70:
        return "高风险"
    if score >= 45:
        return "中高风险"
    if score >= 25:
        return "中等风险"
    return "低风险"


def load_enterprise_invoice_features(enterprise_id: str) -> dict[str, Any] | None:
    """从 MySQL 拉取单企业发票特征（enterprise_id 与 taxpayer_id 同为 MD5 hex）。"""
    from app.db.mysql import U, fetch_all
    from app.services.enterprise_id import mysql_taxpayer_id

    tid = mysql_taxpayer_id(enterprise_id)
    scbm_rows = fetch_all(
        f"""
        SELECT {U('i.sign')} AS sign_cn, LEFT(d.scbm, 4) AS scbm4, COUNT(*) AS cnt
        FROM syx_invoice_details d
        JOIN syx_invoice i ON d.invoice_id = i.id
        WHERE d.taxpayer_id = %s AND d.scbm IS NOT NULL AND d.scbm <> ''
        GROUP BY i.sign, LEFT(d.scbm, 4)
        """,
        (tid,),
    )
    buy, sell = [], []
    for r in scbm_rows:
        sign = r.get("sign_cn") or ""
        prefix = r.get("scbm4") or ""
        n = int(r.get("cnt") or 0)
        if "进" in sign:
            buy.extend([prefix] * max(1, min(n, 50)))
        elif "销" in sign:
            sell.extend([prefix] * max(1, min(n, 50)))

    inv = fetch_all(
        f"""
        SELECT COUNT(*) AS cnt,
               SUM(CASE WHEN LOWER(zfbz) IN ('true','1','yes') THEN 1 ELSE 0 END) AS void_cnt
        FROM syx_invoice WHERE taxpayer_id = %s
        """,
        (tid,),
    )
    invoice_cnt = int(inv[0]["cnt"]) if inv else 0

    red = fetch_all(
        "SELECT COUNT(*) AS cnt FROM syx_red_invoices_info WHERE taxpayer_id = %s",
        (tid,),
    )
    red_cnt = int(red[0]["cnt"]) if red else 0

    # 按对手方金额（销项：购方；进项：销方）
    cp_rows = fetch_all(
        f"""
        SELECT CASE WHEN {U('sign')} LIKE '%%销%%' THEN gfsh ELSE xfsh END AS cp,
               SUM(COALESCE(jshj, 0)) AS amt
        FROM syx_invoice
        WHERE taxpayer_id = %s AND (zfbz IS NULL OR LOWER(zfbz) IN ('','n','0','false'))
        GROUP BY CASE WHEN {U('sign')} LIKE '%%销%%' THEN gfsh ELSE xfsh END
        """,
        (tid,),
    )
    amounts = [_f(r["amt"]) for r in cp_rows if r.get("cp")]

    nums = fetch_all(
        """
        SELECT fphm FROM syx_invoice
        WHERE taxpayer_id = %s AND fphm REGEXP '^[0-9]+$'
        ORDER BY CAST(fphm AS UNSIGNED)
        LIMIT 5000
        """,
        (tid,),
    )
    invoice_numbers = [r["fphm"] for r in nums]

    if invoice_cnt == 0 and not buy and not sell:
        return None

    return {
        "enterprise_id": tid,
        "buy_scbm": buy,
        "sell_scbm": sell,
        "red_cnt": red_cnt,
        "invoice_cnt": invoice_cnt,
        "amounts_by_counterparty": amounts,
        "invoice_numbers": invoice_numbers,
    }


def analyze_enterprise(enterprise_id: str) -> dict[str, Any] | None:
    feats = load_enterprise_invoice_features(enterprise_id)
    if not feats:
        return None
    result = analyze_invoice_bundle(
        buy_scbm=feats["buy_scbm"],
        sell_scbm=feats["sell_scbm"],
        red_cnt=feats["red_cnt"],
        invoice_cnt=feats["invoice_cnt"],
        amounts_by_counterparty=feats["amounts_by_counterparty"],
        invoice_numbers=feats["invoice_numbers"],
    )
    result["enterprise_id"] = enterprise_id
    return result


def analyze_metrics_batch(rows: list[tuple[str, str, str, str | None]], max_n: int = 60) -> dict[str, Any]:
    """
    rows: [(enterprise_id, display_label, industry_l1, display_name), ...]
    优先读 PG 预计算；缺失项回退 MySQL。
    """
    from app.services.engine_features_store import load_fraud_features_batch

    batch = rows[:max_n]
    eids = [r[0] for r in batch]
    pre = load_fraud_features_batch(eids)
    allow_mysql = os.getenv("FRAUD_ALLOW_MYSQL_FALLBACK", "false").lower() in ("1", "true", "yes")
    miss = [eid for eid in eids if eid not in pre]
    if miss:
        logger.warning(
            "fraud precompute miss %d/%d (fallback=%s)",
            len(miss),
            len(eids),
            "mysql" if allow_mysql else "skip",
        )

    results = []
    features = []
    mysql_fallback_n = 0
    for eid, label, ind, name in batch:
        r = pre.get(eid)
        if not r:
            if not allow_mysql:
                continue
            try:
                r = analyze_enterprise(eid)
                mysql_fallback_n += 1
            except Exception as e:
                logger.debug("fraud skip %s: %s", eid, e)
                continue
        if not r:
            continue
        r = dict(r)
        r["display_label"] = label
        r["industry_l1"] = ind
        r["display_name"] = name
        results.append(r)
        if r.get("_precomputed") and r.get("pyod_score") is not None:
            features.append(None)  # placeholder
        else:
            features.append(
                [
                    r["scbm_mismatch"]["score"],
                    r["red_invoice"]["score"],
                    r["concentration"]["score"],
                    r["sequence"]["gap_ratio"] * 100,
                ]
            )

    # 仅对非预计算项重算 pyod；预计算已有 pyod_score
    need_pyod_idx = [i for i, f in enumerate(features) if f is not None]
    if need_pyod_idx:
        mat = np.array([features[i] for i in need_pyod_idx])
        anomaly = pyod_anomaly_scores(mat)
        for j, i in enumerate(need_pyod_idx):
            results[i]["pyod_score"] = round(float(anomaly[j]) * 100, 2)

    for r in results:
        if "pyod_score" not in r:
            r["pyod_score"] = 0.0

    def _score(r: dict) -> float:
        return float(r.get("composite_score") or r.get("fraud_composite_score") or 0)

    flagged = [r for r in results if r.get("signals") or r.get("pyod_score", 0) >= 70]
    flagged.sort(key=_score, reverse=True)

    signal_counts = Counter()
    for r in results:
        for s in r.get("signals") or []:
            signal_counts[s] += 1

    industry_l1 = rows[0][2] if rows and len({r[2] for r in rows}) == 1 else None
    if not results and batch:
        return {
            "dimension": "industry" if industry_l1 else "overall",
            "industry_l1": industry_l1 or "整体",
            "sample_count": 0,
            "requested_count": len(batch),
            "flagged_count": 0,
            "signal_counts": {},
            "avg_composite": 0,
            "top_flags": [],
            "confidence": "inferred",
            "coverage": "precompute_missing",
            "precomputed_hits": len(eids) - len(miss),
            "precompute_miss": len(miss),
            "mysql_fallback_n": mysql_fallback_n,
            "trace": {
                "table": "enterprise_engine_features",
                "field": "fraud_composite_score",
                "detail_table": "syx_invoice_details",
                "query_id": "Q_fraud_industry_slice",
            },
        }
    return {
        "dimension": "industry" if industry_l1 else "overall",
        "industry_l1": industry_l1 or "整体",
        "sample_count": len(results),
        "flagged_count": len(flagged),
        "signal_counts": dict(signal_counts),
        "avg_composite": round(sum(_score(r) for r in results) / len(results), 2) if results else 0,
        "top_flags": [
            {
                "enterprise_id": r.get("enterprise_id"),
                "display_label": r.get("display_label"),
                "display_name": r.get("display_name"),
                "industry_l1": r.get("industry_l1"),
                "fraud_composite_score": _score(r),
                "composite_score": _score(r),
                "fraud_risk_level": r.get("risk_level") or r.get("fraud_risk_level"),
                "scbm_mismatch_score": (r.get("scbm_mismatch") or {}).get("score")
                if isinstance(r.get("scbm_mismatch"), dict)
                else r.get("scbm_mismatch_score"),
                "red_invoice_score": (r.get("red_invoice") or {}).get("score")
                if isinstance(r.get("red_invoice"), dict)
                else r.get("red_invoice_score"),
                "concentration_score": (r.get("concentration") or {}).get("score")
                if isinstance(r.get("concentration"), dict)
                else r.get("concentration_score"),
                "signals": r.get("signals") or [],
                "pyod_score": r.get("pyod_score", 0),
            }
            for r in flagged[:15]
        ],
        "confidence": "computed",
        "precomputed_hits": len(eids) - len(miss),
        "mysql_fallback_n": mysql_fallback_n,
        "trace": {
            "table": "enterprise_engine_features",
            "field": "fraud_composite_score",
            "detail_table": "syx_invoice_details",
            "query_id": "Q_fraud_industry_slice",
        },
    }


def analyze_industry_slice(industry_l1: str | None = None, limit: int = 60) -> dict[str, Any]:
    """兼容入口：自行从 PG 取 ID（可能在无事件循环环境调用）。"""
    from sqlalchemy import text

    from app.db.urls import get_sync_engine

    engine = get_sync_engine()
    sql = "SELECT enterprise_id, display_label, industry_l1, display_name FROM core_metrics"
    args: dict = {}
    if industry_l1:
        sql += " WHERE industry_l1 = :ind"
        args["ind"] = industry_l1
    sql += f" LIMIT {int(limit)}"
    with engine.connect() as conn:
        rows = [(r[0], r[1], r[2], r[3]) for r in conn.execute(text(sql), args)]
    return analyze_metrics_batch(rows, max_n=limit)


def fake_mismatch_sample() -> dict[str, Any]:
    """验收用：构造明显进销错配假样本。"""
    # 进项：钢材；销项：软件服务 — 完全不重合
    return analyze_invoice_bundle(
        buy_scbm=["1080", "1080", "1081", "1070"],
        sell_scbm=["3040", "3040", "3070"],
        red_cnt=25,
        invoice_cnt=100,
        amounts_by_counterparty=[900_000, 50_000, 30_000, 20_000],
        invoice_numbers=["1001", "1002", "1003", "1010", "1011", "1020"],
        industry_red_ratio=0.02,
    )
