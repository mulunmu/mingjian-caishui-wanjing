"""
源库 schema 审计：列出每张候选表的实际行数 + 覆盖企业数 + 关键枚举列取值分布。

用途：数据扩容前摸清「还能抽什么」，避免字段遗漏。只读，不改库。

用法:
  cd backend
  python -m app.etl.source_audit
"""
from __future__ import annotations

import os

import pymysql

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_USER = os.getenv("MYSQL_USER", "risk_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "risk_pass")
MYSQL_DB = os.getenv("MYSQL_DB", "bill_tax_fusion_dwd_standrad")


def conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=30,
        read_timeout=600,
    )


# 表名 -> 用于覆盖数统计的列（都是 taxpayer_id）
TABLES = [
    "syx_enterprise_info",
    "syx_credit_level",
    "syx_tax_payment",
    "syx_vat_arrears_tax",
    "syx_tax_illega",
    "syx_auditing",
    "syx_invoice",
    "syx_invoice_details",
    "syx_invoice_overview_info",
    "syx_red_invoices_info",
    "syx_declaration_correction",
    "syx_declaration_correction_records",
    "syx_declaration_latest_correction",
    "syx_social_declaration",
    "syx_tax_interaction",
    "syx_tax_value_added",
    "syx_tax_value_added_header",
    "syx_corporate_income_season",
    "syx_corporate_income_season_header",
    "syx_corporate_income_year",
    "syx_corporate_income_year_cbzc",
    "syx_corporate_income_year_qysr",
    "syx_corporate_income_year_qjfy",
    "syx_corporate_income_year_jmsds",
    "syx_corporate_income_year_msjjsr",
    "syx_corporate_income_year_yffy",
    "syx_corporate_income_year_zgxc",
    "syx_corporate_income_year_gxjs",
    "syx_corporate_income_year_enterprise_gdinfo",
    "syx_corporate_income_year_enterprise_info",
    "syx_tax_type_determination",
    "syx_taxpayer_type",
    "syx_approved_collection_info_dqde",
    "syx_approved_collection_info_sds",
    "syx_approved_collection_info_yhs",
    "syx_bank_account_info",
    "syx_address_phone_info",
    "syx_investor_info",
    "syx_enterprise_change_info",
    "syx_general_institution_info",
    "syx_sub_institution_info",
    "syx_transaction",
]

# 枚举列探查：表 -> [(列, 是否需 U() 乱码修复)]
ENUM_PROBES = {
    "syx_invoice": ["sign", "fpzl_zh", "state", "risk_level", "invoice_status"],
    "syx_invoice_details": ["specific_business_type", "sign"],
    "syx_tax_payment": ["tax_type", "tax_status", "tax_attributes"],
    "syx_social_declaration": ["fee_type", "type", "levy_project_name"],
    "syx_tax_interaction": ["status", "bank_product"],
    "syx_declaration_correction": ["levy_project_name", "state"],
    "syx_tax_value_added": ["taxpayer_type", "project_name"],
    "syx_corporate_income_year": ["table_type", "project_name"],
    "syx_taxpayer_type": ["taxpayer_type"],
}


def probe_enum(cur, table: str, cols: list[str]) -> None:
    for col in cols:
        try:
            cur.execute(
                f"SELECT `{col}` AS v, COUNT(*) AS c FROM `{table}` "
                f"WHERE `{col}` IS NOT NULL AND `{col}` <> '' GROUP BY `{col}` "
                f"ORDER BY c DESC LIMIT 15"
            )
            rows = cur.fetchall()
            print(f"    [{col}]")
            for r in rows:
                v = str(r["v"])[:60]
                print(f"        {v!r}: {r['c']}")
        except Exception as exc:
            print(f"    [{col}] probe failed: {exc}")


def main() -> None:
    with conn() as c:
        with c.cursor() as cur:
            print("== 行数 / 覆盖企业数（distinct taxpayer_id） ==")
            for t in TABLES:
                try:
                    cur.execute(f"SELECT COUNT(*) AS n FROM `{t}`")
                    total = cur.fetchone()["n"]
                    if total == 0:
                        print(f"{t:45s} rows=0 (空)")
                        continue
                    cur.execute(
                        f"SELECT COUNT(DISTINCT taxpayer_id) AS d FROM `{t}` "
                        f"WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''"
                    )
                    distinct = cur.fetchone()["d"]
                    print(f"{t:45s} rows={total:>10,d}  enterprises={distinct}")
                except Exception as exc:
                    print(f"{t:45s} ERROR: {exc}")

            print("\n== 枚举列取值分布 ==")
            for table, cols in ENUM_PROBES.items():
                # 先确认表非空
                cur.execute(f"SELECT COUNT(*) AS n FROM `{table}`")
                if cur.fetchone()["n"] == 0:
                    continue
                print(f"\n[{table}]")
                probe_enum(cur, table, cols)


if __name__ == "__main__":
    main()
