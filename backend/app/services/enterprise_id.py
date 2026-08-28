"""enterprise_id ↔ MySQL taxpayer_id 统一映射（PG 与 MySQL 对齐）"""
from __future__ import annotations

import hashlib
import logging
import re

logger = logging.getLogger(__name__)

_MD5_HEX = re.compile(r"^[0-9a-f]{32}$")


def enterprise_id_of(taxpayer_id: str) -> str:
    """
    ETL：源库 taxpayer_id 通常为 32 位 hex MD5；
    若为明文税号则再 hash 一次。
    """
    tid = (taxpayer_id or "").strip().lower()
    if _MD5_HEX.fullmatch(tid):
        return tid
    return hashlib.md5(tid.encode("utf-8")).hexdigest()


def mysql_taxpayer_id(enterprise_id: str) -> str:
    """运行时：PG core_metrics.enterprise_id → MySQL WHERE taxpayer_id。"""
    return (enterprise_id or "").strip().lower()


def describe_taxpayer_id(sample: str | None) -> dict:
    s = (sample or "").strip()
    if not s:
        return {"format": "empty", "is_md5_hex": False, "length": 0}
    low = s.lower()
    return {
        "format": "md5_hex" if _MD5_HEX.fullmatch(low) else "other",
        "is_md5_hex": bool(_MD5_HEX.fullmatch(low)),
        "length": len(s),
        "sample_prefix": low[:8],
    }


def verify_mysql_taxpayer_link(enterprise_id: str, mysql_fetch_one) -> dict:
    """
    校验 PG enterprise_id 能否在 MySQL 命中发票。
    mysql_fetch_one(sql, args) -> dict | None
    """
    tid = mysql_taxpayer_id(enterprise_id)
    row = mysql_fetch_one(
        "SELECT COUNT(*) AS cnt FROM syx_invoice WHERE taxpayer_id = %s",
        (tid,),
    )
    cnt = int((row or {}).get("cnt") or 0)
    return {
        "enterprise_id": enterprise_id,
        "mysql_taxpayer_id": tid,
        "invoice_rows": cnt,
        "linked": cnt > 0,
    }
