"""编码与数据链路自检（可独立运行）

对当前 MySQL 实测结论（2026-08）：
- 中文列（bureau / register_province / industry_type / sign / project_name）均为
  双重 UTF-8 乱码，U()=CONVERT(...latin1...utf8mb4) 可正确还原。
- 数据.sql 文本里看起来像「广东」≠ 库内存储字节；必须以 SELECT HEX() 为准。
- ASCII 列（credit_level）套 U() 无害。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.mysql import U, fetch_all


def _probe(sql: str, label: str, ok_fn) -> dict:
    rows = fetch_all(sql)
    n_ok = sum(1 for r in rows if ok_fn(r))
    print(f"=== {label} ({n_ok}/{len(rows)}) ===")
    for r in rows[:5]:
        print(r)
    return {"n": len(rows), "ok": n_ok, "pass": n_ok >= max(1, len(rows) // 3)}


def main() -> int:
    print("=== counts ===")
    for t in ("syx_enterprise_info", "syx_invoice", "syx_invoice_details"):
        r = fetch_all(f"SELECT COUNT(*) AS c FROM {t}")
        print(t, r[0]["c"])

    print("=== taxpayer_id format ===")
    rows = fetch_all("SELECT taxpayer_id FROM syx_enterprise_info LIMIT 5")
    for r in rows:
        tid = (r["taxpayer_id"] or "").strip().lower()
        ok = bool(re.fullmatch(r"[0-9a-f]{32}", tid))
        print(tid[:12], "len=", len(tid), "md5_hex=", ok)
        assert ok, f"taxpayer_id not md5 hex: {tid}"

    bureau = _probe(
        f"""
        SELECT HEX(LEFT(bureau, 4)) AS hex_raw, bureau AS raw,
               {U("bureau")} AS fixed
        FROM syx_enterprise_info
        WHERE bureau IS NOT NULL AND bureau <> ''
        LIMIT 12
        """,
        "bureau (enterprise)",
        lambda r: bool(re.search(r"[\u4e00-\u9fff]", str(r.get("fixed") or ""))),
    )

    sign = _probe(
        f"""
        SELECT HEX(LEFT(sign, 3)) AS hex_raw, sign AS raw,
               {U("sign")} AS fixed
        FROM syx_invoice
        WHERE sign IS NOT NULL AND sign <> ''
        LIMIT 12
        """,
        "sign (invoice)",
        lambda r: bool(re.search(r"[进销]", str(r.get("fixed") or ""))),
    )

    print("POLICY: Chinese text cols -> U() REQUIRED (proven on live MySQL)")
    print("POLICY: Do NOT judge encoding from 数据.sql text dump alone — use HEX()")

    print("=== sensitive source cols (presence only) ===")
    cols = fetch_all(
        """
        SELECT COLUMN_NAME AS c
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'syx_enterprise_info'
          AND COLUMN_NAME IN (
            'taxpayer_name','legal_person_name','legal_person_id_number',
            'register_address','business_address','business_scope',
            'legal_person_mobile_phone','finance_manager_name',
            'finance_manager_id_number','tax_collector_name'
          )
        """
    )
    print("sensitive_cols_present", [c["c"] for c in cols])

    if not bureau["pass"] or not sign["pass"]:
        print("FAIL: encoding probe")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
