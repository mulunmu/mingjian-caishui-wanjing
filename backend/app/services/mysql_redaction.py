"""MySQL 源库二次脱敏：启动/ETL 可自动调用，不可逆 UPDATE。

安全语义（fail-closed）：
- probe 无法确认脱敏状态时，视为 needs_redaction=True（宁可多脱敏，不可漏）。
- 守卫探测全部敏感列，而非仅 business_scope/bureau_detail 两列。
"""
from __future__ import annotations

import logging

from app.db.mysql import fetch_all, get_conn

logger = logging.getLogger(__name__)

# 直接置 NULL 的列（无法哈希的语义列）
REDACT_NULL_COLS = [
    "business_scope",
    "bureau_detail",
]

# 哈希保留或置 NULL 的 PII 列（已为 32 位 hex 则保留，否则置 NULL）
FORCE_HASH_OR_NULL = [
    "taxpayer_name",
    "legal_person_name",
    "legal_person_id_number",
    "legal_person_mobile_phone",
    "register_address",
    "business_address",
    "finance_manager_name",
    "finance_manager_id_number",
    "finance_manager_mobile_phone",
    "tax_collector_name",
    "tax_collector_id_number",
    "tax_collector_mobile_phone",
    "operation_location_mobile",
    "register_location_mobile",
]

# 股东类表的表名提示 + PII 列提示（防御性脱敏，见 redact_shareholder_tables）
SHAREHOLDER_TABLE_HINTS = ("shareholder", "stockholder", "gudong", "share_holder", "partner", "investor")
SHAREHOLDER_PII_TOKENS = ("name", "id_number", "id_card", "idcard", "card_no", "cert", "identity", "mobile", "phone", "address", "tel")
PROTECTED_COLUMNS = {"id", "taxpayer_id", "enterprise_id", "company_id", "corp_id"}


def _table_columns(table: str) -> set[str]:
    rows = fetch_all(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table,),
    )
    return {r["column_name"] for r in rows}


def _is_protected(col: str) -> bool:
    low = col.lower()
    return low in PROTECTED_COLUMNS or low.endswith(("_date", "_time", "_at"))


def _null_cols_available(cols: set[str]) -> list[str]:
    return [c for c in REDACT_NULL_COLS if c in cols]


def _hash_cols_available(cols: set[str]) -> list[str]:
    return [c for c in FORCE_HASH_OR_NULL if c in cols]


def probe_redaction_state() -> dict:
    """统计全部敏感列的疑似明文行数；任一非空即 needs_redaction。出错 fail-closed。"""
    try:
        cols = _table_columns("syx_enterprise_info")
        null_cols = _null_cols_available(cols)
        hash_cols = _hash_cols_available(cols)
        if not null_cols and not hash_cols:
            return {"ok": False, "error": "no_sensitive_columns_found", "needs_redaction": False}

        exprs: list[str] = []
        for c in null_cols:
            exprs.append(
                f"SUM(CASE WHEN {c} IS NOT NULL AND {c}<>'' THEN 1 ELSE 0 END) AS `{c}_n`"
            )
        for c in hash_cols:
            exprs.append(
                f"SUM(CASE WHEN {c} IS NOT NULL AND {c}<>'' "
                f"AND {c} NOT REGEXP '^[0-9a-fA-F]{{32}}$' THEN 1 ELSE 0 END) AS `{c}_n`"
            )
        stats = fetch_all(f"SELECT {', '.join(exprs)} FROM syx_enterprise_info")[0]
        plaintext_cells = sum(int(stats.get(k) or 0) for k in stats)
        out = {**stats, "needs_redaction": plaintext_cells > 0, "plaintext_cells": plaintext_cells}
        return out
    except Exception as exc:
        # fail-closed：探测失败 → 当作需要脱敏
        return {"ok": False, "error": str(exc), "needs_redaction": True}


def apply_redaction() -> int:
    """对 syx_enterprise_info 存在的敏感列执行脱敏（仅更新实际存在的列）。"""
    cols = _table_columns("syx_enterprise_info")
    sets: list[str] = [f"{c}=NULL" for c in _null_cols_available(cols)]
    for c in _hash_cols_available(cols):
        sets.append(f"{c}=IF({c} REGEXP '^[0-9a-fA-F]{{32}}$', {c}, NULL)")
    if not sets:
        return 0
    sql = f"UPDATE syx_enterprise_info SET {', '.join(sets)}"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            n = cur.rowcount
        conn.commit()
    return n


def discover_shareholder_tables() -> list[str]:
    """发现库内股东/投资人/合伙人相关表（防御性，无则空）。"""
    try:
        rows = fetch_all(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()"
        )
    except Exception as exc:
        logger.warning("shareholder table discover failed: %s", exc)
        return []
    return [r["table_name"] for r in rows if any(h in (r["table_name"] or "").lower() for h in SHAREHOLDER_TABLE_HINTS)]


def _shareholder_pii_cols(table: str) -> list[str]:
    cols = _table_columns(table)
    out = []
    for c in cols:
        low = c.lower()
        if _is_protected(c):
            continue
        if any(tok in low for tok in SHAREHOLDER_PII_TOKENS):
            out.append(c)
    return out


def redact_shareholder_tables() -> dict:
    """股东表防御性脱敏：PII 列哈希保留或置 NULL，join 键/主键不动。"""
    tables = discover_shareholder_tables()
    result: dict = {"tables": [], "rows": 0}
    for table in tables:
        pii = _shareholder_pii_cols(table)
        if not pii:
            continue
        sets = [
            f"{c}=IF({c} REGEXP '^[0-9a-fA-F]{{32}}$', {c}, NULL)" for c in pii
        ]
        sql = f"UPDATE {table} SET {', '.join(sets)}"
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    n = cur.rowcount
                conn.commit()
            result["tables"].append(table)
            result["rows"] += n
            logger.info("redacted shareholder table %s (rows=%s, cols=%s)", table, n, pii)
        except Exception as exc:
            logger.warning("shareholder redact failed on %s: %s", table, exc)
    return result


def run_startup_redaction(*, force: bool = False) -> dict:
    """启动时自动脱敏：probe 有明文 / probe 失败 / force 时 apply，并联动股东表。"""
    probe = probe_redaction_state()
    if probe.get("error"):
        # fail-closed：状态不可知 → 仍强制脱敏，避免明文残留
        logger.warning("MySQL redaction probe failed, forcing redaction (fail-closed): %s", probe["error"])
        force = True

    shareholder = {}
    try:
        shareholder = redact_shareholder_tables()
    except Exception as exc:
        logger.warning("shareholder redaction error: %s", exc)

    if not force and not probe.get("needs_redaction"):
        return {
            "applied": False,
            "skipped": True,
            "reason": "already_clean",
            "shareholder": shareholder,
            **probe,
        }

    try:
        n = apply_redaction()
        after = probe_redaction_state()
        logger.info("MySQL redaction applied, rows≈%s, after=%s", n, after)
        return {"applied": True, "rows": n, "before": probe, "after": after, "shareholder": shareholder}
    except Exception as exc:
        logger.warning("MySQL redaction apply failed: %s", exc)
        return {"applied": False, "error": str(exc), "shareholder": shareholder, **probe}
