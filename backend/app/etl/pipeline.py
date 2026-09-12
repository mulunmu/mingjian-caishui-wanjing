"""
ETL: MySQL 原始明细 → PostgreSQL core_metrics / industry_benchmark / legal_events

用法:
  cd backend
  python -m app.etl.pipeline
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.models.core_metrics import CoreMetrics, IndustryBenchmark, LegalEvent
from app.models.financials import EnterpriseFinancials
from app.db.session import Base
from app.etl import profiles as profile_etl

logger = logging.getLogger(__name__)

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_USER = os.getenv("MYSQL_USER", "risk_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "risk_pass")
MYSQL_DB = os.getenv("MYSQL_DB", "bill_tax_fusion_dwd_standrad")

PG_URL = os.getenv(
    "DATABASE_URL_SYNC",
    os.getenv("DATABASE_URL", "postgresql+asyncpg://risk_user:risk_pass@localhost:5432/risk_db").replace(
        "postgresql+asyncpg://", "postgresql://"
    ),
)

INDUSTRY_MAP = [
    (re.compile(r"批发|零售|贸易|经销|商贸|超市|电商"), "批发零售"),
    (re.compile(r"制造|加工|生产|金属|机械|设备|电器|电子|化工|纺织|食品|家具"), "制造"),
    (re.compile(r"建筑|装修|装饰|土木|工程安装|房屋|基建"), "建筑"),
    (re.compile(r"软件|信息|互联网|数据|通信|计算机|网络|系统集成|IT"), "IT软件"),
    (re.compile(r"服务|咨询|设计|物流|运输|餐饮|酒店|广告|租赁|中介|教育|医疗|健康|金融|保险"), "服务"),
]


def U(col: str) -> str:
    """SQL 表达式：修复双重 UTF-8 乱码。"""
    return f"CONVERT(BINARY CONVERT({col} USING latin1) USING utf8mb4)"


def fix_mojibake(s: str | None) -> str:
    """兜底：客户端侧再尝试 latin1→utf8。"""
    if not s:
        return ""
    try:
        fixed = s.encode("latin1").decode("utf-8")
        if fixed != s:
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return s


def map_industry(raw: str | None) -> tuple[str, str]:
    raw = (raw or "").strip() or "未知"
    raw = fix_mojibake(raw)
    for pattern, big in INDUSTRY_MAP:
        if pattern.search(raw):
            return big, raw
    return "其他", raw


# 受控 L2 词汇表：把原文行业类型归入粗粒度 L2，避免原文特异性反推企业（词汇表有限、不可反推）
L2_BUCKETS: dict[str, list[tuple[re.Pattern, str]]] = {
    "批发零售": [
        (re.compile(r"批发|经销|贸易|进出口|外贸"), "批发贸易"),
        (re.compile(r"零售|超市|电商|商贸|连锁|百货|便利店"), "零售电商"),
    ],
    "制造": [
        (re.compile(r"电子|电器|通信|计算机|半导体|仪器|仪表"), "电子设备"),
        (re.compile(r"机械|设备|金属|钢铁|汽车|船舶|航空|通用"), "装备制造"),
        (re.compile(r"化工|制药|生物|橡胶|塑料|建材|矿物"), "化工材料"),
        (re.compile(r"食品|饮料|纺织|服装|家具|造纸|印刷|木材"), "轻工制造"),
    ],
    "建筑": [
        (re.compile(r"装修|装饰|幕墙|安装|设计"), "装饰装修"),
        (re.compile(r"房屋|住宅|土木|市政|基建|路桥|工程"), "工程建设"),
    ],
    "IT软件": [
        (re.compile(r"软件|系统|开发|互联网|平台|信息|数据|系统集成"), "软件服务"),
        (re.compile(r"通信|网络|电子|硬件|芯片|半导体"), "电子信息"),
    ],
    "服务": [
        (re.compile(r"物流|运输|货运|仓储|配送|快递|供应链"), "物流运输"),
        (re.compile(r"餐饮|酒店|住宿|旅游|食品|娱乐"), "餐饮住宿"),
        (re.compile(r"金融|保险|投资|担保|小额|基金|典当|融资"), "金融服务"),
        (re.compile(r"医疗|健康|养老|医药|医院"), "医疗健康"),
        (re.compile(r"教育|培训|咨询|中介|广告|物业|保洁|租赁|设计"), "专业服务"),
    ],
}


def coarse_l2(big: str, raw: str) -> str:
    """把原文行业细类归入受控 L2；无匹配回退到大类，保证 L2 词汇表有限。"""
    for pattern, label in L2_BUCKETS.get(big, []):
        if pattern.search(raw):
            return label
    return big


from app.services.enterprise_id import enterprise_id_of
def _dec(v: Any, default: float = 0.0) -> Decimal:
    try:
        if v is None or v == "":
            return Decimal(str(default))
        return Decimal(str(v))
    except Exception:
        return Decimal(str(default))


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _report_year(end_date: Any) -> str | None:
    """从报告期 end_date 抽取年份；缺失/不可解析 → None（弃权，不编造）。"""
    if not end_date:
        return None
    if hasattr(end_date, "year"):
        return str(end_date.year)
    s = str(end_date)
    return s[:4] if len(s) >= 4 and s[:4].isdigit() else None


def _scale_label(employees: Any, capital: Any) -> str:
    emp = int(employees or 0)
    cap = _f(capital)
    if emp >= 300 or cap >= 5_000_000:
        return "中型"
    if emp >= 20 or cap >= 1_000_000:
        return "小型"
    return "小微"


def mysql_conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        use_unicode=True,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=30,
        read_timeout=600,
        init_command="SET NAMES utf8mb4",
    )


def fetch_all(sql: str, args: tuple | None = None) -> list[dict]:
    with mysql_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return list(cur.fetchall())


def load_enterprises() -> dict[str, dict]:
    rows = fetch_all(
        f"""
        SELECT taxpayer_id,
               {U('industry_type')} AS industry_type,
               {U('register_province')} AS register_province,
               {U('register_city')} AS register_city,
               employees_number, register_capital, create_time
        FROM syx_enterprise_info
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        ORDER BY create_time DESC
        """
    )
    by_id: dict[str, dict] = {}
    for r in rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        if eid in by_id:
            continue
        industry_l1, industry_raw = map_industry(r.get("industry_type"))
        industry_l2 = coarse_l2(industry_l1, industry_raw)
        province = ((r.get("register_province") or "未知").strip()) or "未知"
        city = ((r.get("register_city") or province).strip()) or province
        scale = _scale_label(r.get("employees_number"), r.get("register_capital"))
        by_id[eid] = {
            "enterprise_id": eid,
            "industry_l1": industry_l1,
            "industry_l2": industry_l2,
            "province": province,
            "city": city,
            "scale_label": scale,
            "display_label": f"{province}·{industry_l1}·{scale}",
        }
    return by_id


def load_credit() -> dict[str, dict]:
    rows = fetch_all(
        f"""
        SELECT taxpayer_id,
               {U('credit_level')} AS credit_level,
               credit_point, year
        FROM syx_credit_level
        WHERE taxpayer_id IS NOT NULL
        ORDER BY year DESC
        """
    )
    out: dict[str, dict] = {}
    level_score = {"A": 90, "B": 75, "C": 55, "D": 35, "M": 40, "不参评": 50, "暂无": 50}
    for r in rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        if eid in out:
            continue
        level = (r.get("credit_level") or "暂无").strip()[:10]
        score = _f(r.get("credit_point"))
        if score <= 0:
            score = float(level_score.get(level, 50))
        out[eid] = {"credit_level": level if level else "暂无", "credit_score": score}
    return out


def load_payment() -> dict[str, dict]:
    rows = fetch_all(
        """
        SELECT taxpayer_id, payment_date, jkqx
        FROM syx_tax_payment
        WHERE taxpayer_id IS NOT NULL
        """
    )
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # on_time, total
    for r in rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        pd, dq = r.get("payment_date"), r.get("jkqx")
        if pd is None or dq is None:
            continue
        stats[eid][1] += 1
        if pd <= dq:
            stats[eid][0] += 1
    return {
        eid: {"tax_on_time_rate": (a / b if b else 0.0)}
        for eid, (a, b) in stats.items()
    }


def load_arrears() -> dict[str, int]:
    rows = fetch_all(
        """
        SELECT taxpayer_id, COUNT(*) cnt
        FROM syx_vat_arrears_tax
        WHERE taxpayer_id IS NOT NULL
        GROUP BY taxpayer_id
        """
    )
    return {enterprise_id_of(r["taxpayer_id"]): int(r["cnt"]) for r in rows}


_HIGH_SEV_KEYWORDS = (
    "严重",
    "偷税",
    "逃避缴纳税款",
    "虚开",
    "骗税",
    "犯罪",
    "重大",
    "逃税",
)


def _illegal_severity(desc: str) -> str:
    """源表无独立严重度列：按违法类型/事实描述关键词区分 H/M，避免全量标 H 导致与 tax_violation 双扣。"""
    text = desc or ""
    if any(k in text for k in _HIGH_SEV_KEYWORDS):
        return "H"
    return "M"


def load_illegal() -> tuple[dict[str, int], dict[str, int], list[dict]]:
    """仅 syx_tax_illega → tax_violation。

    返回 (illegal_cnt, high_severity_cnt, events)。
    high_severity 是 illegal 的子集，不得与 illegal_cnt 恒等复制。
    """
    rows = fetch_all(
        f"""
        SELECT taxpayer_id,
               {U('wfwzlxmc')} AS wfwzlxmc,
               {U('zywfwzsdmc')} AS zywfwzsdmc,
               larq, djrq
        FROM syx_tax_illega
        WHERE taxpayer_id IS NOT NULL
        """
    )
    cnt: dict[str, int] = defaultdict(int)
    high_cnt: dict[str, int] = defaultdict(int)
    events: list[dict] = []
    for r in rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        desc = (r.get("wfwzlxmc") or r.get("zywfwzsdmc") or "税务违法")[:200]
        sev = _illegal_severity(desc)
        cnt[eid] += 1
        if sev == "H":
            high_cnt[eid] += 1
        events.append(
            {
                "enterprise_id": eid,
                "event_type": "tax_violation",
                "severity": sev,
                # 明文描述可能含企业特异文本；落库截断并由下游脱敏/不对外暴露
                "event_date": r.get("larq") or r.get("djrq"),
                # 不落库企业特异原文，仅保留类型标签，降低明文残留风险
                "description": "税务违法" if sev != "H" else "高严重度税务违法",
                "source": "syx_tax_illega",
            }
        )
    return dict(cnt), dict(high_cnt), events


def load_auditing() -> list[dict]:
    """syx_auditing 税务稽查案件 → tax_audit 事件（仍属税务侧，非司法失信源）。"""
    try:
        rows = fetch_all(
            f"""
            SELECT taxpayer_id,
                   {U('ajmc')} AS ajmc,
                   {U('wfwzlxmc')} AS wfwzlxmc,
                   {U('jclxmc')} AS jclxmc,
                   {U('jcztmc')} AS jcztmc,
                   aydjrq
            FROM syx_auditing
            WHERE taxpayer_id IS NOT NULL
            """
        )
    except Exception as exc:
        logger.warning("auditing load failed: %s", exc)
        return []
    events: list[dict] = []
    for r in rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        events.append(
            {
                "enterprise_id": eid,
                "event_type": "tax_audit",
                "severity": "M",
                "event_date": r.get("aydjrq"),
                # 不落库企业特异原文（ajmc/wfwzlxmc/jclxmc），仅保留类型标签，降低明文残留风险
                "description": "税务稽查案件",
                "source": "syx_auditing",
            }
        )
    return events


def load_invoice() -> dict[str, dict]:
    # 销项营收用 hjje（不含税），与 vat_revenue / finance_revenue 口径对齐；勿用 jshj（价税合计）
    rows = fetch_all(
        f"""
        SELECT taxpayer_id,
               COUNT(*) AS cnt,
               SUM(CASE
                     WHEN {U('sign')} LIKE '%%销%%' OR HEX(sign) LIKE 'C3A9%%'
                     THEN COALESCE(CAST(NULLIF(hjje,'') AS DECIMAL(20,4)), 0) ELSE 0
                   END) AS sales_amt,
               COUNT(DISTINCT DATE_FORMAT(kprq, '%%Y-%%m')) AS months
        FROM syx_invoice
        WHERE taxpayer_id IS NOT NULL
          AND (zfbz IS NULL OR LOWER(zfbz) IN ('', 'n', '0', 'false', '否'))
        GROUP BY taxpayer_id
        """
    )
    out = {}
    for r in rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        months = max(int(r["months"] or 1), 1)
        cnt = int(r["cnt"] or 0)
        out[eid] = {
            "invoice_cnt": cnt,
            "invoice_revenue": _f(r["sales_amt"]),
            "invoice_monthly_avg": int(round(cnt / months)),
        }
    return out


def load_red_invoice() -> dict[str, int]:
    try:
        rows = fetch_all(
            """
            SELECT taxpayer_id, COUNT(*) cnt
            FROM syx_red_invoices_info
            WHERE taxpayer_id IS NOT NULL
            GROUP BY taxpayer_id
            """
        )
        return {enterprise_id_of(r["taxpayer_id"]): int(r["cnt"]) for r in rows}
    except Exception as e:
        logger.warning("red invoice load failed: %s", e)
        return {}


def load_vat_revenue() -> dict[str, float]:
    rows = fetch_all(
        f"""
        SELECT taxpayer_id,
               MAX(COALESCE(general_year_accumulative_amount,0)
                   + COALESCE(current_year_accumulative_goods,0)
                   + COALESCE(current_year_accumulative_service,0)) AS rev
        FROM syx_tax_value_added
        WHERE taxpayer_id IS NOT NULL
          AND ({U('project_name')} LIKE '%%应税销售额%%'
               OR {U('project_name')} LIKE '%%销售额%%'
               OR column_sequence IN ('1','1.0'))
        GROUP BY taxpayer_id
        """
    )
    if not rows:
        # 品目过滤无命中时弃权（不回退为全表 SUM，避免把进项/免税行计入销售额）
        logger.warning("load_vat_revenue: no rows matched 销售额品目 filter (with U()); abstaining")
        return {}
    return {enterprise_id_of(r["taxpayer_id"]): _f(r["rev"]) for r in rows}


def _fin_key(name: str) -> str:
    """归一化行项目名用于精确匹配：去序号/减加前缀/括号/非汉字。"""
    n = (name or "").strip()
    n = re.sub(r"^[一二三四五六七八九十]+、", "", n)      # 「一、」等序号
    n = re.sub(r"^(减|加|其中)[：:]", "", n)             # 「减：」「加：」
    n = re.sub(r"[（(].*?[）)]", "", n)                   # 去括号（如「（亏损以-号填列）」）
    return re.sub(r"[^一-鿿]", "", n)            # 只留汉字


# 行项目别名（值 = 归一化后的精确名，优先级从高到低）。精确匹配避免「营业收入」误命中「主营业务收入」。
_BALANCE_ALIASES: dict[str, list[str]] = {
    "total_assets": ["资产总计", "资产合计"],
    "total_liab": ["负债合计", "负债总计"],
    "current_assets": ["流动资产合计"],
    "current_liab": ["流动负债合计"],
    "cash_equiv": ["货币资金"],
    "inventory": ["存货"],
    "accounts_receivable": ["应收账款"],
    "fixed_assets": ["固定资产净额", "固定资产账面价值", "固定资产净值"],
    "short_loan": ["短期借款"],
    "owner_equity": ["所有者权益或股东权益合计", "所有者权益合计", "所有者权益或股东权益总计", "所有者权益总计"],
    "retained_earnings": ["未分配利润"],
}
_PROFIT_ALIASES: dict[str, list[str]] = {
    # 仅用「营业收入」；勿并列「主营业务收入」以免同表多行时跨别名非确定性少计/混用
    "revenue": ["营业收入"],
    "cost": ["营业成本"],
    "tax_surcharge": ["税金及附加"],
    "sell_expense": ["销售费用", "营业费用"],
    "admin_expense": ["管理费用"],
    "finance_expense": ["财务费用"],
    "operating_profit": ["营业利润"],
    "total_profit": ["利润总额"],
    "income_tax": ["所得税费用", "所得税"],
    "net_profit": ["净利润"],
}
_CASHFLOW_ALIASES: dict[str, list[str]] = {
    "operating_cf": ["经营活动产生的现金流量净额"],
    "investing_cf": ["投资活动产生的现金流量净额"],
    "financing_cf": ["筹资活动产生的现金流量净额"],
}


def _extract_field_rows(rows: list[dict], aliases: dict[str, list[str]], value_key: str) -> dict[str, dict]:
    """按别名精确匹配行项目；同一企业只取同一报告期（该表最新 end_date）的字段，避免跨期混用。"""
    alias_to_field: dict[str, str] = {}
    for field, names in aliases.items():
        for nm in names:
            alias_to_field.setdefault(nm, field)

    # eid → end_date → {field: value}；同期内首条命中保留（rows 已按 end_date DESC）
    by_eid_date: dict[str, dict[Any, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        ed = r.get("end_date")
        if not eid or ed is None:
            continue
        key = _fin_key(r.get("project_name") or "")
        field = alias_to_field.get(key)
        if field and field not in by_eid_date[eid][ed]:
            by_eid_date[eid][ed][field] = _f(r.get(value_key))

    out: dict[str, dict] = {}
    for eid, by_date in by_eid_date.items():
        latest = max(by_date.keys())
        out[eid] = by_date[latest]
    return out


def _ratio(num: float, den: float, lo: float, hi: float) -> float:
    """比率：分母绝对值 <= 1 视为弃权置 0，否则夹在 [lo, hi]。"""
    if abs(den) <= 1.0:
        return 0.0
    return max(lo, min(hi, num / den))


def load_finance() -> dict[str, dict]:
    """抽取完整三大报表行项目 + 计算四能力比率。

    返回 {eid: {财务代理字段 + 四能力比率 + 原始行项目金额}}，
    由 build_metrics 取比率字段写入 CoreMetrics，build_financials 取原始行项目写 EnterpriseFinancials。
    """
    profit_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('project_name')} AS project_name,
               current_year_accumulative_amount AS cur,
               last_year_accumulative_amount AS prev,
               end_date
        FROM syx_tax_finance_profit_year
        WHERE taxpayer_id IS NOT NULL
        ORDER BY end_date DESC
        """
    )
    bal_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('project_name')} AS project_name, ending_balance, end_date
        FROM syx_tax_finance_balance_year
        WHERE taxpayer_id IS NOT NULL
        ORDER BY end_date DESC
        """
    )
    cf_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('project_name')} AS project_name,
               COALESCE(bnljje, bqje) AS bnljje,
               end_date
        FROM syx_cash_flow
        WHERE taxpayer_id IS NOT NULL
        ORDER BY end_date DESC
        """
    )

    profit = _extract_field_rows(profit_rows, _PROFIT_ALIASES, "cur")
    prev_profit = _extract_field_rows(profit_rows, _PROFIT_ALIASES, "prev")
    balance = _extract_field_rows(bal_rows, _BALANCE_ALIASES, "ending_balance")
    cashflow = _extract_field_rows(cf_rows, _CASHFLOW_ALIASES, "bnljje")

    eids = set(profit) | set(balance) | set(cashflow)
    # 最新报告期（取三表 end_date 的最大值，用于回填 report_year）
    latest_end: dict[str, Any] = {}
    for row in profit_rows + bal_rows + cf_rows:
        eid = enterprise_id_of(row.get("taxpayer_id") or "")
        ed = row.get("end_date")
        if not eid or not ed:
            continue
        if eid not in latest_end or ed > latest_end[eid]:
            latest_end[eid] = ed

    out: dict[str, dict] = {}
    for eid in eids:
        p = profit.get(eid, {})
        pp = prev_profit.get(eid, {})
        b = balance.get(eid, {})
        c = cashflow.get(eid, {})

        revenue = p.get("revenue", 0.0)
        cost = p.get("cost", 0.0)
        net_profit = p.get("net_profit", 0.0)
        total_assets = b.get("total_assets", 0.0)
        total_liab = b.get("total_liab", 0.0)
        current_assets = b.get("current_assets", 0.0)
        current_liab = b.get("current_liab", 0.0)
        inventory = b.get("inventory", 0.0)
        accounts_receivable = b.get("accounts_receivable", 0.0)
        owner_equity = b.get("owner_equity", 0.0)
        operating_cf = c.get("operating_cf", 0.0)

        # 四能力比率（弃权置 0）
        current_ratio = _ratio(current_assets, current_liab, -10.0, 50.0)
        quick_ratio = _ratio(current_assets - inventory, current_liab, -10.0, 50.0)
        debt_ratio = _ratio(total_liab, total_assets, -2.0, 3.0)
        receivables_turnover = _ratio(revenue, accounts_receivable, 0.0, 1000.0)
        inventory_turnover = _ratio(cost, inventory, 0.0, 1000.0)
        asset_turnover = _ratio(revenue, total_assets, 0.0, 100.0)
        gross_margin = _ratio(revenue - cost, revenue, -5.0, 2.0)
        net_margin = _ratio(net_profit, revenue, -5.0, 2.0)
        roe = _ratio(net_profit, owner_equity, -5.0, 5.0)
        roa = _ratio(net_profit, total_assets, -5.0, 5.0)

        revenue_prev = pp.get("revenue", 0.0)
        profit_prev = pp.get("net_profit", 0.0)
        revenue_yoy = _ratio(revenue - revenue_prev, revenue_prev, -2.0, 5.0)
        profit_yoy = _ratio(net_profit - profit_prev, profit_prev, -2.0, 5.0)

        # 现金流健康度（沿用旧口径）
        if operating_cf > 0 and net_margin >= 0:
            cf_level = "健康"
        elif operating_cf >= 0 or net_margin >= -0.05:
            cf_level = "一般"
        else:
            cf_level = "承压"

        out[eid] = {
            # 财务代理字段（向后兼容 CoreMetrics 旧列）
            "finance_revenue": revenue,
            "profit_margin": max(-2.0, min(2.0, net_margin)),
            "revenue_yoy": revenue_yoy,
            "profit_yoy": profit_yoy,
            "debt_ratio": debt_ratio,
            "cash_flow_net": operating_cf,
            "cash_flow_level": cf_level,
            # 四能力比率（新列）
            "current_ratio": current_ratio,
            "quick_ratio": quick_ratio,
            "gross_margin": gross_margin,
            "net_margin": net_margin,
            "roe": roe,
            "roa": roa,
            "receivables_turnover": receivables_turnover,
            "inventory_turnover": inventory_turnover,
            "asset_turnover": asset_turnover,
            "has_financial_statements": total_assets > 0 and revenue > 0,
            "report_year": _report_year(latest_end.get(eid)),
            # 原始行项目（写 EnterpriseFinancials）
            "total_assets": total_assets,
            "total_liab": total_liab,
            "current_assets": current_assets,
            "current_liab": current_liab,
            "cash_equiv": b.get("cash_equiv", 0.0),
            "inventory": inventory,
            "accounts_receivable": accounts_receivable,
            "fixed_assets": b.get("fixed_assets", 0.0),
            "short_loan": b.get("short_loan", 0.0),
            "owner_equity": owner_equity,
            "retained_earnings": b.get("retained_earnings", 0.0),
            "revenue": revenue,
            "cost": cost,
            "tax_surcharge": p.get("tax_surcharge", 0.0),
            "sell_expense": p.get("sell_expense", 0.0),
            "admin_expense": p.get("admin_expense", 0.0),
            "finance_expense": p.get("finance_expense", 0.0),
            "operating_profit": p.get("operating_profit", 0.0),
            "total_profit": p.get("total_profit", 0.0),
            "income_tax": p.get("income_tax", 0.0),
            "net_profit": net_profit,
            "operating_cf": operating_cf,
            "investing_cf": c.get("investing_cf", 0.0),
            "financing_cf": c.get("financing_cf", 0.0),
        }
    return out


def build_financials(ents: dict[str, dict], finance: dict[str, dict]) -> list[EnterpriseFinancials]:
    """从 load_finance 结果构造 EnterpriseFinancials（原始行项目 + 比率，用于报告溯源）。"""
    now = datetime.now(timezone.utc)
    rows: list[EnterpriseFinancials] = []
    for eid in ents:
        f = finance.get(eid, {})
        rows.append(
            EnterpriseFinancials(
                enterprise_id=eid,
                report_year=f.get("report_year"),
                total_assets=_dec(f.get("total_assets", 0)),
                total_liab=_dec(f.get("total_liab", 0)),
                current_assets=_dec(f.get("current_assets", 0)),
                current_liab=_dec(f.get("current_liab", 0)),
                cash_equiv=_dec(f.get("cash_equiv", 0)),
                inventory=_dec(f.get("inventory", 0)),
                accounts_receivable=_dec(f.get("accounts_receivable", 0)),
                fixed_assets=_dec(f.get("fixed_assets", 0)),
                short_loan=_dec(f.get("short_loan", 0)),
                owner_equity=_dec(f.get("owner_equity", 0)),
                retained_earnings=_dec(f.get("retained_earnings", 0)),
                revenue=_dec(f.get("revenue", 0)),
                cost=_dec(f.get("cost", 0)),
                tax_surcharge=_dec(f.get("tax_surcharge", 0)),
                sell_expense=_dec(f.get("sell_expense", 0)),
                admin_expense=_dec(f.get("admin_expense", 0)),
                finance_expense=_dec(f.get("finance_expense", 0)),
                operating_profit=_dec(f.get("operating_profit", 0)),
                total_profit=_dec(f.get("total_profit", 0)),
                income_tax=_dec(f.get("income_tax", 0)),
                net_profit=_dec(f.get("net_profit", 0)),
                operating_cf=_dec(f.get("operating_cf", 0)),
                investing_cf=_dec(f.get("investing_cf", 0)),
                financing_cf=_dec(f.get("financing_cf", 0)),
                current_ratio=_dec(f.get("current_ratio", 0)),
                quick_ratio=_dec(f.get("quick_ratio", 0)),
                debt_ratio=_dec(f.get("debt_ratio", 0)),
                receivables_turnover=_dec(f.get("receivables_turnover", 0)),
                inventory_turnover=_dec(f.get("inventory_turnover", 0)),
                asset_turnover=_dec(f.get("asset_turnover", 0)),
                gross_margin=_dec(f.get("gross_margin", 0)),
                net_margin=_dec(f.get("net_margin", 0)),
                roe=_dec(f.get("roe", 0)),
                roa=_dec(f.get("roa", 0)),
                revenue_yoy=_dec(f.get("revenue_yoy", 0)),
                profit_yoy=_dec(f.get("profit_yoy", 0)),
                updated_at=now,
            )
        )
    return rows


def load_social() -> dict[str, dict]:
    """社保趋势：按时间轴前半/后半「缴费人数」均值比较；人数缺失时弃权为稳定。

    禁止用记录条数前后半比较（几乎恒「稳定」却驱动扣分）。
    """
    rows = fetch_all(
        """
        SELECT taxpayer_id, begin_date, end_date,
               COALESCE(payment_people_number, enrollment_number, 0) AS headcount
        FROM syx_social_declaration
        WHERE taxpayer_id IS NOT NULL
        ORDER BY begin_date
        """
    )
    by_eid: dict[str, list[tuple]] = defaultdict(list)
    for r in rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        bd = r.get("begin_date")
        if not bd:
            continue
        by_eid[eid].append((bd, _f(r.get("headcount"))))
    out = {}
    for eid, pts in by_eid.items():
        pts = sorted(pts, key=lambda x: x[0])
        months = len({(d.year, d.month) for d, _ in pts if d})
        headcounts = [h for _, h in pts if h > 0]
        if months >= 6 and len(headcounts) >= 4:
            mid = len(headcounts) // 2
            first = sum(headcounts[:mid]) / max(mid, 1)
            second = sum(headcounts[mid:]) / max(len(headcounts) - mid, 1)
            if first > 0 and second > first * 1.15:
                trend = "增长"
            elif first > 0 and second < first * 0.85:
                trend = "缩减"
            else:
                trend = "稳定"
        else:
            trend = "稳定"
        out[eid] = {"social_trend": trend, "social_months": months}
    return out


def load_loans() -> dict[str, dict]:
    try:
        rows = fetch_all(
            """
            SELECT taxpayer_id, COUNT(*) cnt
            FROM syx_tax_interaction
            WHERE taxpayer_id IS NOT NULL
            GROUP BY taxpayer_id
            """
        )
        return {
            enterprise_id_of(r["taxpayer_id"]): {"loan_cnt": int(r["cnt"]), "loan_amount": 0.0}
            for r in rows
        }
    except Exception as e:
        logger.warning("loan load failed: %s", e)
        return {}


def build_metrics() -> tuple[
    list[CoreMetrics],
    list[LegalEvent],
    list[EnterpriseFinancials],
    list[profile_etl.EnterpriseInvoiceProfile],
    list[profile_etl.EnterpriseTaxProfile],
]:
    logger.info("Loading enterprises from MySQL...")
    ents = load_enterprises()
    credit = load_credit()
    payment = load_payment()
    arrears = load_arrears()
    illegal_cnt, high_sev_cnt, illegal_events = load_illegal()
    audit_events = load_auditing()
    invoice = load_invoice()
    red = load_red_invoice()
    vat = load_vat_revenue()
    finance = load_finance()
    social = load_social()
    loans = load_loans()
    logger.info("Loading invoice/tax profiles...")
    invoice_profile = profile_etl.load_invoice_profile()
    tax_profile = profile_etl.load_tax_profile()
    logger.info(
        "Aggregating %d enterprises (invoice profile %d, tax profile %d)...",
        len(ents), len(invoice_profile), len(tax_profile),
    )

    now = datetime.now(timezone.utc)
    metrics: list[CoreMetrics] = []
    for eid, base in ents.items():
        c = credit.get(eid, {})
        p = payment.get(eid, {})
        inv = invoice.get(eid, {})
        fin = finance.get(eid, {})
        soc = social.get(eid, {})
        loan = loans.get(eid, {})
        invp = invoice_profile.get(eid, {})
        taxp = tax_profile.get(eid, {})

        vat_rev = vat.get(eid, 0.0)
        inv_rev = inv.get("invoice_revenue", 0.0)
        fin_rev = fin.get("finance_revenue", 0.0)
        refs = [x for x in (vat_rev, inv_rev, fin_rev) if abs(x) > 1]
        if len(refs) >= 2:
            mean = sum(refs) / len(refs)
            deviation = statistics.pstdev(refs) / abs(mean) if mean else 0.0
        else:
            deviation = 0.0

        # 高危为违法子集，禁止与 tax_violation_cnt 恒等复制
        high_sev = high_sev_cnt.get(eid, 0)
        avg_price = invp.get("avg_unit_price", 0.0) or 0.0
        max_price = invp.get("max_unit_price", 0.0) or 0.0
        price_ratio = max_price / avg_price if avg_price > 0 else 0.0
        metrics.append(
            CoreMetrics(
                enterprise_id=eid,
                display_label=base["display_label"],
                industry_l1=base["industry_l1"],
                industry_l2=base["industry_l2"][:80],
                province=base["province"][:50],
                city=base["city"][:50],
                scale_label=base["scale_label"],
                credit_level=c.get("credit_level", "暂无"),
                credit_score=_dec(c.get("credit_score", 50)),
                tax_on_time_rate=_dec(p.get("tax_on_time_rate", 0)),  # 无缴款记录 → 0=弃权，禁止伪造 0.5/0.85
                tax_arrears_cnt=arrears.get(eid, 0),
                tax_violation_cnt=illegal_cnt.get(eid, 0),
                high_severity_cnt=high_sev,
                # 源库无失信/被执行表：保持 False，且评估层标注 coverage=tax_illegal_only
                # 勿将 False 解读为「已核实无失信」
                is_dishonesty=False,
                is_execution=False,
                loan_cnt=int(taxp.get("tax_loan_apply_cnt") or loan.get("loan_cnt", 0)),
                loan_amount=_dec(taxp.get("tax_loan_amount") or loan.get("loan_amount", 0)),
                vat_revenue=_dec(vat_rev),
                invoice_revenue=_dec(inv_rev),
                finance_revenue=_dec(fin_rev),
                revenue_deviation=_dec(min(deviation, 9.9999)),
                invoice_monthly_avg=inv.get("invoice_monthly_avg", 0),
                invoice_cnt=inv.get("invoice_cnt", 0),
                red_invoice_cnt=red.get(eid, 0),
                social_trend=soc.get("social_trend", "稳定"),
                social_months=soc.get("social_months", 0),
                profit_margin=_dec(fin.get("profit_margin", 0)),
                revenue_yoy=_dec(fin.get("revenue_yoy", 0)),
                profit_yoy=_dec(fin.get("profit_yoy", 0)),
                debt_ratio=_dec(fin.get("debt_ratio", 0)),
                cash_flow_net=_dec(fin.get("cash_flow_net", 0)),
                cash_flow_level=fin.get("cash_flow_level", "一般"),
                current_ratio=_dec(fin.get("current_ratio", 0)),
                quick_ratio=_dec(fin.get("quick_ratio", 0)),
                gross_margin=_dec(fin.get("gross_margin", 0)),
                net_margin=_dec(fin.get("net_margin", 0)),
                roe=_dec(fin.get("roe", 0)),
                roa=_dec(fin.get("roa", 0)),
                receivables_turnover=_dec(fin.get("receivables_turnover", 0)),
                inventory_turnover=_dec(fin.get("inventory_turnover", 0)),
                asset_turnover=_dec(fin.get("asset_turnover", 0)),
                has_financial_statements=bool(fin.get("has_financial_statements", False)),
                customer_concentration=_dec(invp.get("top_customer_share", 0)),
                supplier_concentration=_dec(invp.get("top_supplier_share", 0)),
                category_concentration=_dec(invp.get("top_category_share", 0)),
                vat_burden=_dec(taxp.get("vat_burden", 0)),
                income_tax_burden=_dec(taxp.get("income_tax_burden", 0)),
                correction_times=int(taxp.get("correction_times", 0)),
                social_headcount=int(taxp.get("social_headcount", 0)),
                tax_late_penalty_cnt=int(taxp.get("tax_late_penalty_cnt", 0)),
                change_cnt=int(taxp.get("change_cnt", 0)),
                void_invoice_cnt=int(invp.get("void_invoice_cnt", 0)),
                unit_price_ratio=_dec(round(price_ratio, 4)),
                updated_at=now,
            )
        )

    # 可读名「企业N」：按 enterprise_id（MD5）稳定排序，保证同名跨报告一致、可串联单企业分析
    metrics.sort(key=lambda m: m.enterprise_id)
    for i, m in enumerate(metrics, 1):
        m.display_name = f"企业{i}"

    events = [
        LegalEvent(
            enterprise_id=e["enterprise_id"],
            event_type=e["event_type"],
            severity=e["severity"],
            event_date=e["event_date"],
            description=e["description"],
            source=e["source"],
            created_at=now,
        )
        for e in (illegal_events + audit_events)
        if e["enterprise_id"] in ents
    ]
    financials = build_financials(ents, finance)
    invoice_profiles = profile_etl.build_invoice_profiles(ents, invoice_profile)
    tax_profiles = profile_etl.build_tax_profiles(ents, tax_profile)
    return metrics, events, financials, invoice_profiles, tax_profiles


def build_benchmarks(metrics: list[CoreMetrics]) -> list[IndustryBenchmark]:
    now = datetime.now(timezone.utc)
    by_ind: dict[str, list[CoreMetrics]] = defaultdict(list)
    for m in metrics:
        by_ind[m.industry_l1].append(m)

    result = []
    for ind, items in by_ind.items():
        credits = [float(x.credit_score) for x in items]
        ontime = [float(x.tax_on_time_rate) for x in items]
        devs = [float(x.revenue_deviation) for x in items]
        invs = [float(x.invoice_monthly_avg) for x in items]
        margins = [float(x.profit_margin) for x in items]
        debts = [float(x.debt_ratio) for x in items]
        high = sum(1 for x in items if x.credit_level in ("C", "D", "M") or x.tax_violation_cnt > 0)
        # 财务四能力比率基准仅取「有完整三大报表」的样本，避免 0（弃权）拉低均值
        fin_items = [x for x in items if x.has_financial_statements]
        curr_ratios = [float(x.current_ratio) for x in fin_items]
        quick_ratios = [float(x.quick_ratio) for x in fin_items]
        gross_margins = [float(x.gross_margin) for x in fin_items]
        net_margins = [float(x.net_margin) for x in fin_items]
        roes = [float(x.roe) for x in fin_items]
        roas = [float(x.roa) for x in fin_items]
        recv_turn = [float(x.receivables_turnover) for x in fin_items]
        inv_turn = [float(x.inventory_turnover) for x in fin_items]
        asset_turn = [float(x.asset_turnover) for x in fin_items]

        def avg(xs: list[float]) -> float:
            return sum(xs) / len(xs) if xs else 0.0

        def p50(xs: list[float]) -> float:
            return statistics.median(xs) if xs else 0.0

        result.append(
            IndustryBenchmark(
                industry_l1=ind,
                sample_count=len(items),
                avg_credit_score=_dec(avg(credits)),
                avg_tax_on_time_rate=_dec(avg(ontime)),
                avg_revenue_deviation=_dec(avg(devs)),
                avg_invoice_monthly=_dec(avg(invs)),
                avg_profit_margin=_dec(avg(margins)),
                avg_debt_ratio=_dec(avg(debts)),
                p50_credit_score=_dec(p50(credits)),
                p50_invoice_monthly=_dec(p50(invs)),
                high_risk_rate=_dec(high / len(items) if items else 0),
                avg_current_ratio=_dec(avg(curr_ratios)),
                avg_quick_ratio=_dec(avg(quick_ratios)),
                avg_gross_margin=_dec(avg(gross_margins)),
                avg_net_margin=_dec(avg(net_margins)),
                avg_roe=_dec(avg(roes)),
                avg_roa=_dec(avg(roas)),
                avg_receivables_turnover=_dec(avg(recv_turn)),
                avg_inventory_turnover=_dec(avg(inv_turn)),
                avg_asset_turnover=_dec(avg(asset_turn)),
                updated_at=now,
            )
        )
    return result


def _migrate_columns(engine) -> None:
    """给已存在的表补新增列（create_all 不 ALTER 既有表），幂等。"""
    _add: list[tuple[str, str, str]] = [
        ("core_metrics", "current_ratio", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "quick_ratio", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "gross_margin", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "net_margin", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "roe", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "roa", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "receivables_turnover", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "inventory_turnover", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "asset_turnover", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "has_financial_statements", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("core_metrics", "customer_concentration", "NUMERIC(8,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "supplier_concentration", "NUMERIC(8,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "category_concentration", "NUMERIC(8,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "vat_burden", "NUMERIC(8,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "income_tax_burden", "NUMERIC(8,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "correction_times", "INTEGER NOT NULL DEFAULT 0"),
        ("core_metrics", "social_headcount", "INTEGER NOT NULL DEFAULT 0"),
        ("core_metrics", "tax_late_penalty_cnt", "INTEGER NOT NULL DEFAULT 0"),
        ("core_metrics", "change_cnt", "INTEGER NOT NULL DEFAULT 0"),
        ("core_metrics", "void_invoice_cnt", "INTEGER NOT NULL DEFAULT 0"),
        ("core_metrics", "unit_price_ratio", "NUMERIC(18,4) NOT NULL DEFAULT 0"),
        ("core_metrics", "display_name", "VARCHAR(32)"),
        ("industry_benchmark", "avg_current_ratio", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("industry_benchmark", "avg_quick_ratio", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("industry_benchmark", "avg_gross_margin", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("industry_benchmark", "avg_net_margin", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("industry_benchmark", "avg_roe", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("industry_benchmark", "avg_roa", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("industry_benchmark", "avg_receivables_turnover", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("industry_benchmark", "avg_inventory_turnover", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
        ("industry_benchmark", "avg_asset_turnover", "NUMERIC(12,4) NOT NULL DEFAULT 0"),
    ]
    with engine.begin() as conn:
        for table, col, ddl in _add:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ddl}"))
        # 回填可读名「企业N」（幂等，只处理 display_name 为空的存量行，与 ETL 的 enterprise_id 排序一致）
        conn.execute(text(
            "UPDATE core_metrics SET display_name = '企业' || sub.rn FROM ("
            "SELECT enterprise_id, ROW_NUMBER() OVER (ORDER BY enterprise_id) AS rn "
            "FROM core_metrics WHERE display_name IS NULL"
            ") sub WHERE core_metrics.enterprise_id = sub.enterprise_id"
        ))


def write_to_pg(
    metrics: list[CoreMetrics],
    events: list[LegalEvent],
    benchmarks: list[IndustryBenchmark],
    financials: list[EnterpriseFinancials],
    invoice_profiles: list[profile_etl.EnterpriseInvoiceProfile],
    tax_profiles: list[profile_etl.EnterpriseTaxProfile],
) -> dict:
    from app.etl.engine_features import build_engine_features, write_engine_features

    from app.db.urls import get_sync_engine

    engine = get_sync_engine()
    # 指标表原子重写：TRUNCATE + 重灌 + commit 在同一事务内，读端在 commit 前仍见旧数据，
    # 不会读空/读不到（替代原 DROP 重建）。结论/会话/用户表保留；engine 表由 write_engine_features 原子写。
    Base.metadata.create_all(engine)
    _migrate_columns(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        session.execute(
            text(
                "TRUNCATE core_metrics, legal_events, industry_benchmark, "
                "enterprise_financials, enterprise_invoice_profile, enterprise_tax_profile CASCADE"
            )
        )
        session.bulk_save_objects(metrics)
        session.bulk_save_objects(events)
        session.bulk_save_objects(benchmarks)
        session.bulk_save_objects(financials)
        session.bulk_save_objects(invoice_profiles)
        session.bulk_save_objects(tax_profiles)
        session.commit()
        logger.info(
            "Wrote %d core_metrics, %d legal_events, %d industry_benchmark, "
            "%d enterprise_financials, %d invoice_profiles, %d tax_profiles",
            len(metrics),
            len(events),
            len(benchmarks),
            len(financials),
            len(invoice_profiles),
            len(tax_profiles),
        )
        # 同步路径：清空评估缓存，避免 ETL 后最长 TTL 内读到旧批次
        try:
            from app.services import assessment as assessment_svc

            assessment_svc._CACHE["metrics"] = []
            assessment_svc._CACHE["legal_by_ent"] = {}
            assessment_svc._CACHE["loaded_at"] = None
        except Exception as exc:
            logger.warning("assessment cache invalidate after ETL failed: %s", exc)

    engine_features_ok = False
    engine_features_count = 0
    engine_features_error = None
    try:
        feats, snap = build_engine_features()
        write_engine_features(feats, snap)
        engine_features_ok = True
        engine_features_count = len(feats)
        logger.info("Wrote %d enterprise_engine_features + benford snapshot", len(feats))
    except Exception as exc:
        # 默认 FRAUD_ALLOW_MYSQL_FALLBACK=false：预计算失败 → 运行期 fraud/benford 静默 0/0。
        # 必须 ERROR 显性暴露，而不是「将回退 MySQL」的误导性 warning。
        engine_features_error = str(exc)
        logger.error(
            "engine_features ETL FAILED — runtime fraud/benford will be empty "
            "(FRAUD_ALLOW_MYSQL_FALLBACK=false): %s", exc,
        )
    return {
        "engine_features_ok": engine_features_ok,
        "engine_features_count": engine_features_count,
        "engine_features_error": engine_features_error,
    }


def run() -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    metrics, events, financials, invoice_profiles, tax_profiles = build_metrics()
    benchmarks = build_benchmarks(metrics)
    engine_features = write_to_pg(metrics, events, benchmarks, financials, invoice_profiles, tax_profiles)
    by_ind = defaultdict(int)
    for m in metrics:
        by_ind[m.industry_l1] += 1
    summary = {
        "enterprise_count": len(metrics),
        "legal_event_count": len(events),
        "industry_breakdown": dict(by_ind),
        "engine_features": engine_features,
    }
    if engine_features.get("engine_features_ok"):
        logger.info("ETL done: %s", summary)
    else:
        logger.error(
            "ETL done but engine_features MISSING — runtime fraud/benford will be empty: %s",
            summary,
        )
    return summary


if __name__ == "__main__":
    run()
