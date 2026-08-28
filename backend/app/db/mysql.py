"""MySQL 原始库连接（溯源 / 反欺诈 / 真实性）"""
from __future__ import annotations

import os

import pymysql

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_USER = os.getenv("MYSQL_USER", "risk_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "risk_pass")
MYSQL_DB = os.getenv("MYSQL_DB", "bill_tax_fusion_dwd_standrad")

# 修复双重 UTF-8 乱码
U = lambda col: f"CONVERT(BINARY CONVERT({col} USING latin1) USING utf8mb4)"


def get_conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        use_unicode=True,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=120,
        init_command="SET NAMES utf8mb4",
    )


def fetch_all(sql: str, args: tuple | list | None = None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return list(cur.fetchall())
