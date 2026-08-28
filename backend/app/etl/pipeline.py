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
from app.db.session import Base

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
    # zfbz 存 false/true；销项用修复后 sign 或双重编码 HEX
    rows = fetch_all(
        f"""
        SELECT taxpayer_id,
               COUNT(*) AS cnt,
               SUM(CASE
                     WHEN {U('sign')} LIKE '%%销%%' OR HEX(sign) LIKE 'C3A9%%'
                     THEN COALESCE(jshj, 0) ELSE 0
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
        """
        SELECT taxpayer_id,
               MAX(COALESCE(general_year_accumulative_amount,0)
                   + COALESCE(current_year_accumulative_goods,0)
                   + COALESCE(current_year_accumulative_service,0)) AS rev
        FROM syx_tax_value_added
        WHERE taxpayer_id IS NOT NULL
          AND (project_name LIKE '%%应税销售额%%' OR project_name LIKE '%%销售额%%' OR column_sequence IN ('1','1.0'))
        GROUP BY taxpayer_id
        """
    )
    if not rows:
        rows = fetch_all(
            """
            SELECT taxpayer_id,
                   SUM(COALESCE(general_year_accumulative_amount,0)) AS rev
            FROM syx_tax_value_added
            WHERE taxpayer_id IS NOT NULL
            GROUP BY taxpayer_id
            """
        )
    return {enterprise_id_of(r["taxpayer_id"]): _f(r["rev"]) for r in rows}


def load_finance() -> dict[str, dict]:
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
    finance: dict[str, dict] = defaultdict(dict)
    seen_rev: set[str] = set()
    seen_profit: set[str] = set()
    for r in profit_rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        name = r.get("project_name") or ""
        if "营业收入" in name and eid not in seen_rev:
            seen_rev.add(eid)
            cur, prev = _f(r["cur"]), _f(r["prev"])
            finance[eid]["finance_revenue"] = cur
            finance[eid]["revenue_yoy"] = ((cur - prev) / abs(prev)) if abs(prev) > 1 else 0.0
        if "净利润" in name and eid not in seen_profit:
            seen_profit.add(eid)
            cur, prev = _f(r["cur"]), _f(r["prev"])
            finance[eid]["net_profit"] = cur
            finance[eid]["profit_yoy"] = ((cur - prev) / abs(prev)) if abs(prev) > 1 else 0.0

    bal_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('project_name')} AS project_name, ending_balance, end_date
        FROM syx_tax_finance_balance_year
        WHERE taxpayer_id IS NOT NULL
        ORDER BY end_date DESC
        """
    )
    seen_asset: set[str] = set()
    seen_liab: set[str] = set()
    for r in bal_rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        name = r.get("project_name") or ""
        val = _f(r["ending_balance"])
        if ("资产总计" in name or name == "资产合计") and eid not in seen_asset:
            seen_asset.add(eid)
            finance[eid]["total_assets"] = val
        if ("负债合计" in name or "负债总计" in name) and eid not in seen_liab:
            seen_liab.add(eid)
            finance[eid]["total_liab"] = val

    cf_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('project_name')} AS project_name, bnljje, end_date
        FROM syx_cash_flow
        WHERE taxpayer_id IS NOT NULL
        ORDER BY end_date DESC
        """
    )
    seen_cf: set[str] = set()
    for r in cf_rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        if eid in seen_cf:
            continue
        name = r.get("project_name") or ""
        if "经营活动产生的现金流量净额" in name:
            seen_cf.add(eid)
            finance[eid]["cash_flow_net"] = _f(r["bnljje"])

    out: dict[str, dict] = {}
    for eid, d in finance.items():
        rev = d.get("finance_revenue", 0.0)
        profit = d.get("net_profit", 0.0)
        assets = d.get("total_assets", 0.0)
        liab = d.get("total_liab", 0.0)
        cf = d.get("cash_flow_net", 0.0)
        margin = (profit / rev) if abs(rev) > 1 else 0.0
        debt = (liab / assets) if abs(assets) > 1 else 0.0
        if cf > 0 and margin >= 0:
            cf_level = "健康"
        elif cf >= 0 or margin >= -0.05:
            cf_level = "一般"
        else:
            cf_level = "承压"
        out[eid] = {
            "finance_revenue": rev,
            "profit_margin": max(-2.0, min(2.0, margin)),
            "revenue_yoy": max(-2.0, min(5.0, d.get("revenue_yoy", 0.0))),
            "profit_yoy": max(-2.0, min(5.0, d.get("profit_yoy", 0.0))),
            "debt_ratio": max(0.0, min(3.0, debt)),
            "cash_flow_net": cf,
            "cash_flow_level": cf_level,
        }
    return out


def load_social() -> dict[str, dict]:
    rows = fetch_all(
        """
        SELECT taxpayer_id, begin_date, end_date
        FROM syx_social_declaration
        WHERE taxpayer_id IS NOT NULL
        ORDER BY begin_date
        """
    )
    by_eid: dict[str, list] = defaultdict(list)
    for r in rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        if r.get("begin_date"):
            by_eid[eid].append(r["begin_date"])
    out = {}
    for eid, dates in by_eid.items():
        dates = sorted(dates)
        months = len({(d.year, d.month) for d in dates if d})
        if months >= 6:
            mid = len(dates) // 2
            first_half = mid
            second_half = len(dates) - mid
            if second_half > first_half * 1.15:
                trend = "增长"
            elif second_half < first_half * 0.85:
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


def build_metrics() -> tuple[list[CoreMetrics], list[LegalEvent]]:
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
    logger.info("Aggregating %d enterprises...", len(ents))

    now = datetime.now(timezone.utc)
    metrics: list[CoreMetrics] = []
    for eid, base in ents.items():
        c = credit.get(eid, {})
        p = payment.get(eid, {})
        inv = invoice.get(eid, {})
        fin = finance.get(eid, {})
        soc = social.get(eid, {})
        loan = loans.get(eid, {})

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
                tax_on_time_rate=_dec(p.get("tax_on_time_rate", 0.85 if eid in payment else 0.5)),
                tax_arrears_cnt=arrears.get(eid, 0),
                tax_violation_cnt=illegal_cnt.get(eid, 0),
                high_severity_cnt=high_sev,
                # 源库无失信/被执行表：保持 False，且评估层标注 coverage=tax_illegal_only
                # 勿将 False 解读为「已核实无失信」
                is_dishonesty=False,
                is_execution=False,
                loan_cnt=loan.get("loan_cnt", 0),
                loan_amount=_dec(loan.get("loan_amount", 0)),
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
                updated_at=now,
            )
        )

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
    return metrics, events


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
                updated_at=now,
            )
        )
    return result


def write_to_pg(metrics: list[CoreMetrics], events: list[LegalEvent], benchmarks: list[IndustryBenchmark]) -> dict:
    from app.etl.engine_features import build_engine_features, write_engine_features

    from app.db.urls import get_sync_engine

    engine = get_sync_engine()
    # 指标表原子重写：TRUNCATE + 重灌 + commit 在同一事务内，读端在 commit 前仍见旧数据，
    # 不会读空/读不到（替代原 DROP 重建）。结论/会话/用户表保留；engine 表由 write_engine_features 原子写。
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        session.execute(
            text("TRUNCATE core_metrics, legal_events, industry_benchmark CASCADE")
        )
        session.bulk_save_objects(metrics)
        session.bulk_save_objects(events)
        session.bulk_save_objects(benchmarks)
        session.commit()
        logger.info(
            "Wrote %d core_metrics, %d legal_events, %d industry_benchmark",
            len(metrics),
            len(events),
            len(benchmarks),
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
    metrics, events = build_metrics()
    benchmarks = build_benchmarks(metrics)
    engine_features = write_to_pg(metrics, events, benchmarks)
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
