"""MySQL 中文列编码自检 — 验证 U() 双重 UTF-8 修复假设。"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# 进/销 在正确 UTF-8 下首字节常见模式；乱码 é 对应 C3A9
_SIGN_OK = re.compile(r"[进销]")


def check_sign_encoding(sample_limit: int = 50) -> dict:
    """
    抽样 syx_invoice.sign：U(sign) 后应出现「进」「销」。
    若几乎全 miss 而 raw 有 C3A9 等，说明 U() 假设可能错误。
    """
    from app.db.mysql import U, fetch_all

    rows = fetch_all(
        f"""
        SELECT DISTINCT
            sign AS raw_sign,
            {U('sign')} AS fixed_sign,
            HEX(LEFT(sign, 2)) AS hex2
        FROM syx_invoice
        WHERE sign IS NOT NULL AND sign <> ''
        LIMIT %s
        """,
        (sample_limit,),
    )
    if not rows:
        return {"ok": False, "reason": "no_sign_samples", "n": 0}

    ok_fixed = sum(1 for r in rows if _SIGN_OK.search(str(r.get("fixed_sign") or "")))
    ok_raw = sum(1 for r in rows if _SIGN_OK.search(str(r.get("raw_sign") or "")))
    c3a9 = sum(1 for r in rows if str(r.get("hex2") or "").upper().startswith("C3A9"))

    # 期望：fixed 显著多于 raw（乱码库）或两者都高（已正确 UTF-8）
    ok = ok_fixed >= max(2, len(rows) // 10) or (ok_raw >= 2 and ok_fixed >= ok_raw)

    result = {
        "ok": ok,
        "n": len(rows),
        "ok_fixed": ok_fixed,
        "ok_raw": ok_raw,
        "c3a9_like": c3a9,
        "samples": [
            {
                "raw": r.get("raw_sign"),
                "fixed": r.get("fixed_sign"),
                "hex2": r.get("hex2"),
            }
            for r in rows[:5]
        ],
    }
    if not ok:
        logger.error("MySQL sign encoding check FAILED: %s", result)
    else:
        logger.info(
            "MySQL sign encoding check OK (fixed=%d/%d raw=%d c3a9=%d)",
            ok_fixed,
            len(rows),
            ok_raw,
            c3a9,
        )
    return result


def verify_taxpayer_id_samples(limit: int = 5) -> dict:
    from app.db.mysql import fetch_all
    from app.services.enterprise_id import describe_taxpayer_id

    rows = fetch_all(
        "SELECT taxpayer_id FROM syx_enterprise_info WHERE taxpayer_id IS NOT NULL LIMIT %s",
        (limit,),
    )
    samples = [describe_taxpayer_id(r.get("taxpayer_id")) for r in rows]
    all_md5 = all(s.get("is_md5_hex") for s in samples) if samples else False
    return {"ok": all_md5 and len(samples) > 0, "samples": samples, "n": len(samples)}


def check_region_encoding(sample_limit: int = 20) -> dict:
    """抽样 syx_enterprise_info.bureau：U() 后应出现可读中文。"""
    from app.db.mysql import U, fetch_all

    rows = fetch_all(
        f"""
        SELECT bureau AS raw_v, {U('bureau')} AS fixed_v, HEX(LEFT(bureau, 2)) AS hex2
        FROM syx_enterprise_info
        WHERE bureau IS NOT NULL AND bureau <> ''
        LIMIT %s
        """,
        (sample_limit,),
    )
    if not rows:
        return {"ok": False, "reason": "no_bureau_samples", "n": 0}
    _zh = re.compile(r"[\u4e00-\u9fff]")
    ok_fixed = sum(1 for r in rows if _zh.search(str(r.get("fixed_v") or "")))
    ok_raw = sum(1 for r in rows if _zh.search(str(r.get("raw_v") or "")))
    ok = ok_fixed >= max(2, len(rows) // 5)
    result = {
        "ok": ok,
        "n": len(rows),
        "ok_fixed": ok_fixed,
        "ok_raw": ok_raw,
        "policy": "U()_required" if ok_fixed > ok_raw else "raw_may_suffice",
        "samples": [
            {"raw": r.get("raw_v"), "fixed": r.get("fixed_v"), "hex2": r.get("hex2")}
            for r in rows[:3]
        ],
    }
    if not ok:
        logger.error("MySQL bureau encoding check FAILED: %s", result)
    else:
        logger.info(
            "MySQL bureau encoding check OK (fixed=%d/%d raw=%d policy=%s)",
            ok_fixed,
            len(rows),
            ok_raw,
            result["policy"],
        )
    return result


def run_startup_checks() -> dict:
    """启动时调用（同步，应包在 to_thread 内）。"""
    out: dict = {"sign_encoding": None, "region_encoding": None, "taxpayer_id": None}
    try:
        out["sign_encoding"] = check_sign_encoding()
    except Exception as exc:
        out["sign_encoding"] = {"ok": False, "error": str(exc)}
        logger.warning("sign encoding check error: %s", exc)
    try:
        out["region_encoding"] = check_region_encoding()
    except Exception as exc:
        out["region_encoding"] = {"ok": False, "error": str(exc)}
        logger.warning("region encoding check error: %s", exc)
    try:
        out["taxpayer_id"] = verify_taxpayer_id_samples()
    except Exception as exc:
        out["taxpayer_id"] = {"ok": False, "error": str(exc)}
        logger.warning("taxpayer_id check error: %s", exc)
    out["ok"] = bool(
        (out.get("sign_encoding") or {}).get("ok")
        and (out.get("region_encoding") or {}).get("ok")
        and (out.get("taxpayer_id") or {}).get("ok")
    )
    return out
