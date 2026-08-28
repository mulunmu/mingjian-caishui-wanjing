"""生成 200 家企业 core_metrics + legal_events 模拟数据（匿名 display_label），并导入 PostgreSQL

注意：本脚本产出的 dict 键必须与 app.models.core_metrics.CoreMetrics 的实际列完全一致，
否则 import_to_db 里的 CoreMetrics(**row) 会抛 TypeError / AttributeError。
"""
from __future__ import annotations

import asyncio
import os
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# ENT001-ENT010 测试 ID（匿名 display_label，不含具名企业）
LEGACY_COMPANIES = [
    ("ENT001", "广东·制造业·小型", "制造业", "电子设备", "广东", "深圳"),
    ("ENT002", "上海·批发零售·小型", "批发零售", "进出口贸易", "上海", "上海"),
    ("ENT003", "北京·信息技术·中型", "信息技术", "软件服务", "北京", "北京"),
    ("ENT004", "广东·制造业·中型", "制造业", "机械设备", "广东", "广州"),
    ("ENT005", "浙江·新能源·小型", "新能源", "光伏组件", "浙江", "杭州"),
    ("ENT006", "四川·交通运输·小型", "交通运输", "供应链物流", "四川", "成都"),
    ("ENT007", "湖北·医药·小微", "医药", "生物制药", "湖北", "武汉"),
    ("ENT008", "江苏·建筑业·小型", "建筑业", "工程建设", "江苏", "南京"),
    ("ENT009", "天津·交通运输·中型", "交通运输", "港口服务", "天津", "天津"),
    ("ENT010", "重庆·餐饮·小型", "餐饮", "连锁餐饮", "重庆", "重庆"),
]

# 行业分布 200 家
INDUSTRY_PLAN: list[tuple[str, int, list[str]]] = [
    ("制造业", 40, ["电子设备", "机械设备", "汽车零部件", "精密加工", "金属制品"]),
    ("信息技术", 35, ["软件服务", "云计算", "人工智能", "信息系统", "网络安全"]),
    ("批发零售", 30, ["进出口贸易", "批发零售", "连锁超市", "电商运营", "供应链贸易"]),
    ("建筑业", 25, ["工程建设", "装饰装修", "市政工程", "钢结构", "幕墙工程"]),
    ("交通运输", 20, ["供应链物流", "港口服务", "冷链运输", "公路货运", "仓储配送"]),
    ("新能源", 15, ["光伏组件", "风电设备", "储能系统", "锂电池", "充电桩"]),
    ("医药", 15, ["生物制药", "医疗器械", "化学制药", "中药饮片", "医药流通"]),
    ("餐饮", 10, ["连锁餐饮", "中央厨房", "团餐服务", "食品配送", "品牌加盟"]),
    ("金融", 10, ["小额贷款", "融资租赁", "商业保理", "投资咨询", "资产管理"]),
]

REGIONS = [
    ("广东", "深圳"), ("广东", "广州"), ("广东", "东莞"), ("广东", "佛山"),
    ("上海", "上海"), ("北京", "北京"), ("浙江", "杭州"), ("浙江", "宁波"),
    ("江苏", "南京"), ("江苏", "苏州"), ("四川", "成都"), ("湖北", "武汉"),
    ("天津", "天津"), ("重庆", "重庆"), ("山东", "青岛"), ("福建", "厦门"),
    ("河南", "郑州"), ("湖南", "长沙"), ("安徽", "合肥"), ("陕西", "西安"),
]

EVENT_TYPES = ["tax_violation", "tax_arrears", "dishonesty", "execution", "civil_lawsuit", "admin_penalty"]
EVENT_DESCS = {
    "tax_violation": "未按期申报增值税",
    "tax_arrears": "欠缴企业所得税",
    "dishonesty": "列入失信被执行人名单",
    "execution": "被列为被执行对象",
    "civil_lawsuit": "合同纠纷被诉",
    "admin_penalty": "市场监管局行政处罚",
}

# 200 家分段（原 non_listed 段改为 sparse：数据稀疏，测试 coverage 路径）
SEGMENTS: list[tuple[str, int, int]] = [
    ("normal", 1, 100),
    ("high_risk", 101, 130),
    ("anomaly", 131, 150),
    ("excellent", 151, 170),
    ("boundary", 171, 180),
    ("sparse", 181, 190),
    ("new_reg", 191, 200),
]

random.seed(42)


def _eid(n: int) -> str:
    return f"ENT{n:03d}"


def _segment_for(idx: int) -> str:
    for seg, start, end in SEGMENTS:
        if start <= idx <= end:
            return seg
    return "normal"


def _build_industry_assignments() -> list[tuple[str, str]]:
    """返回 200 个 (industry_l1, industry_l2)"""
    out: list[tuple[str, str]] = []
    for l1, count, l2_pool in INDUSTRY_PLAN:
        for _ in range(count):
            out.append((l1, random.choice(l2_pool)))
    random.shuffle(out)
    return out


def _scale_from_label(label: str) -> str:
    """从 '地区·行业·规模' 标签提取规模。"""
    parts = label.split("·")
    return parts[-1] if parts else "小微"


def _display_label(prov: str, l1: str, idx: int) -> tuple[str, str]:
    """返回 (display_label, scale_label)。"""
    if idx <= 10:
        label = next(c[1] for c in LEGACY_COMPANIES if c[0] == _eid(idx))
        return label, _scale_from_label(label)
    scale = random.choice(["小微", "小型", "中型"])
    return f"{prov}·{l1}·{scale}", scale


def _base_row(
    eid: str, label: str, scale: str, l1: str, l2: str, prov: str, city: str, seg: str,
) -> dict:
    """产出键与 CoreMetrics 模型列一一对应。"""
    v = random.randint(5_000_000, 8_000_000_000)
    margin = round(random.uniform(0.02, 0.18), 4)
    months = random.randint(6, 12)
    monthly_avg = random.randint(200, 2500)
    row = {
        "enterprise_id": eid,
        "display_label": label,
        "industry_l1": l1,
        "industry_l2": l2,
        "province": prov,
        "city": city,
        "scale_label": scale,
        "credit_level": "B",
        "credit_score": Decimal("76.00"),
        "tax_on_time_rate": Decimal("0.9200"),
        "tax_arrears_cnt": 0,
        "tax_violation_cnt": 0,
        "high_severity_cnt": 0,
        "is_dishonesty": False,
        "is_execution": False,
        "loan_cnt": 0,
        "loan_amount": Decimal("0"),
        "vat_revenue": Decimal(str(v)),
        "invoice_revenue": Decimal(str(int(v * random.uniform(0.95, 1.05)))),
        "finance_revenue": Decimal(str(int(v * random.uniform(1.0, 1.10)))),
        "revenue_deviation": Decimal(str(round(random.uniform(0.02, 0.12), 4))),
        "invoice_monthly_avg": monthly_avg,
        "invoice_cnt": monthly_avg * months,
        "red_invoice_cnt": 0,
        "social_trend": random.choice(["增长", "稳定", "稳定"]),
        "social_months": months,
        "profit_margin": Decimal(str(margin)),
        "revenue_yoy": Decimal(str(round(random.uniform(-0.05, 0.35), 4))),
        "profit_yoy": Decimal(str(round(random.uniform(-0.2, 0.5), 4))),
        "debt_ratio": Decimal(str(round(random.uniform(0.25, 0.65), 4))),
        "cash_flow_net": Decimal(str(int(v * margin * random.uniform(0.5, 1.5)))),
        "cash_flow_level": random.choice(["健康", "健康", "一般", "承压"]),
        "_segment": seg,
    }

    if seg == "normal":
        row["credit_level"] = random.choice(["A", "A", "B", "B", "B", "C"])
        row["credit_score"] = Decimal(str({"A": 93, "B": 76, "C": 62}[row["credit_level"]] + random.uniform(-4, 4)))
        row["tax_on_time_rate"] = Decimal(str(round(random.uniform(0.82, 0.99), 4)))
        row["tax_arrears_cnt"] = random.randint(0, 1)
        row["tax_violation_cnt"] = random.randint(0, 1)
    elif seg == "high_risk":
        row["credit_level"] = random.choice(["D", "M", "D", "M", "C"])
        row["credit_score"] = Decimal(str(random.uniform(25, 48)))
        row["tax_on_time_rate"] = Decimal(str(round(random.uniform(0.55, 0.78), 4)))
        row["tax_arrears_cnt"] = random.randint(2, 5)
        row["tax_violation_cnt"] = random.randint(2, 4)
        row["high_severity_cnt"] = random.randint(1, 3)
        row["is_dishonesty"] = True
        row["is_execution"] = True
        row["loan_cnt"] = random.randint(1, 4)
        row["loan_amount"] = Decimal(str(random.randint(1_000_000, 50_000_000)))
        row["red_invoice_cnt"] = random.randint(1, 8)
        row["cash_flow_level"] = "承压"
        row["cash_flow_net"] = Decimal(str(-abs(int(v * margin))))
    elif seg == "anomaly":
        row["credit_level"] = random.choice(["B", "C", "C"])
        row["credit_score"] = Decimal(str(random.uniform(55, 72)))
        row["revenue_deviation"] = Decimal(str(round(random.uniform(0.31, 0.55), 4)))
        row["invoice_monthly_avg"] = random.randint(10, 80)
        row["invoice_cnt"] = row["invoice_monthly_avg"] * row["social_months"]
        row["social_trend"] = "缩减"
    elif seg == "excellent":
        row["credit_level"] = "A"
        row["credit_score"] = Decimal(str(random.uniform(92, 99)))
        row["tax_on_time_rate"] = Decimal(str(round(random.uniform(0.96, 1.0), 4)))
        row["tax_arrears_cnt"] = 0
        row["tax_violation_cnt"] = 0
        row["social_trend"] = "增长"
        row["revenue_yoy"] = Decimal(str(round(random.uniform(0.15, 0.45), 4)))
        row["profit_margin"] = Decimal(str(round(random.uniform(0.12, 0.28), 4)))
        row["cash_flow_level"] = "健康"
    elif seg == "boundary":
        row["credit_level"] = random.choice(["B", "C"])
        row["debt_ratio"] = Decimal(str(round(random.uniform(0.92, 0.99), 4)))
        row["invoice_monthly_avg"] = random.choice([0, 0, 5, 12])
        row["invoice_cnt"] = row["invoice_monthly_avg"] * row["social_months"]
        row["cash_flow_level"] = "承压"
        row["cash_flow_net"] = Decimal("0")
        row["revenue_deviation"] = Decimal(str(round(random.uniform(0.2, 0.45), 4)))
    elif seg == "sparse":
        # 数据稀疏：发票/财务/社保缺失，测试评估层 coverage 处理
        row["invoice_revenue"] = Decimal("0")
        row["finance_revenue"] = Decimal("0")
        row["invoice_monthly_avg"] = 0
        row["invoice_cnt"] = 0
        row["red_invoice_cnt"] = 0
        row["social_months"] = 0
        row["social_trend"] = "稳定"
        row["cash_flow_level"] = "一般"
        row["cash_flow_net"] = Decimal("0")
    elif seg == "new_reg":
        row["social_months"] = random.randint(1, 3)
        row["invoice_monthly_avg"] = random.randint(5, 40)
        row["invoice_cnt"] = row["invoice_monthly_avg"] * row["social_months"]
        row["social_trend"] = "稳定"
        row["revenue_yoy"] = Decimal("0")
        row["credit_level"] = random.choice(["B", "C"])

    if eid in {c[0] for c in LEGACY_COMPANIES}:
        leg = next(c for c in LEGACY_COMPANIES if c[0] == eid)
        row["display_label"] = leg[1]
        row["scale_label"] = _scale_from_label(leg[1])
        row["industry_l1"] = leg[2]
        row["industry_l2"] = leg[3]
        row["province"] = leg[4]
        row["city"] = leg[5]
        if eid == "ENT001":
            row.update({
                "credit_level": "B",
                "credit_score": Decimal("76.53"),
                "tax_on_time_rate": Decimal("0.9825"),
                "tax_arrears_cnt": 3,
                "tax_violation_cnt": 0,
                "revenue_deviation": Decimal("0.0552"),
                "invoice_monthly_avg": 847,
                "invoice_cnt": 847 * row["social_months"],
                "social_trend": "增长",
                "cash_flow_level": "承压",
            })
        if eid == "ENT007":
            row.update({"credit_level": "D", "credit_score": Decimal("34.28")})

    return row


def generate_companies() -> list[dict]:
    industries = _build_industry_assignments()
    companies: list[dict] = []
    for idx in range(1, 201):
        eid = _eid(idx)
        seg = _segment_for(idx)
        if idx <= 10:
            leg = next(c for c in LEGACY_COMPANIES if c[0] == eid)
            prov, city, l1, l2, label = leg[4], leg[5], leg[2], leg[3], leg[1]
            scale = _scale_from_label(label)
        else:
            prov, city = random.choice(REGIONS)
            l1, l2 = industries[idx - 1]
            label, scale = _display_label(prov, l1, idx)
        companies.append(_base_row(eid, label, scale, l1, l2, prov, city, seg))
    return companies


def generate_legal_events(companies: list[dict]) -> list[dict]:
    """每家企业 0-3 条，合计约 400 条"""
    events: list[dict] = []
    eid_seq = 1
    for co in companies:
        seg = co["_segment"]
        if seg == "high_risk":
            n = random.randint(2, 3)
            pool = list(EVENT_TYPES)
        elif seg == "excellent":
            n = 0
            pool = EVENT_TYPES
        elif seg == "anomaly":
            n = random.randint(0, 2)
            pool = ["civil_lawsuit", "admin_penalty", "tax_arrears"]
        else:
            n = random.randint(0, 3)
            pool = EVENT_TYPES

        chosen = random.sample(pool, min(n, len(pool))) if n else []
        for et in chosen:
            sv = random.choice(["L", "L", "M", "M", "H"])
            amt = random.randint(5000, 30_000_000) if sv in ("M", "H") else random.randint(1000, 500_000)
            dt = date.today() - timedelta(days=random.randint(30, 900))
            src = "企查查" if et in ("civil_lawsuit", "admin_penalty", "dishonesty", "execution") else "税务数据"
            events.append({
                "id": eid_seq,
                "enterprise_id": co["enterprise_id"],
                "event_type": et,
                "severity": sv,
                "amount_involved": Decimal(str(amt)),
                "event_date": dt,
                "description": EVENT_DESCS[et],
                "source": src,
            })
            eid_seq += 1
    return events


# 与 CoreMetrics 模型列顺序一致的列清单（write_sql / import_to_db 共用）
CORE_COLUMNS = [
    "enterprise_id", "display_label", "industry_l1", "industry_l2",
    "province", "city", "scale_label", "credit_level", "credit_score",
    "tax_on_time_rate", "tax_arrears_cnt", "tax_violation_cnt", "high_severity_cnt",
    "is_dishonesty", "is_execution", "loan_cnt", "loan_amount", "vat_revenue",
    "invoice_revenue", "finance_revenue", "revenue_deviation", "invoice_monthly_avg",
    "invoice_cnt", "red_invoice_cnt", "social_trend", "social_months",
    "profit_margin", "revenue_yoy", "profit_yoy", "debt_ratio",
    "cash_flow_net", "cash_flow_level",
]


def _sql_literal(v) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def write_sql(companies: list[dict], events: list[dict]) -> str:
    lines = [
        "CREATE TABLE IF NOT EXISTS core_metrics (",
        "  enterprise_id VARCHAR(64) PRIMARY KEY, display_label VARCHAR(120),",
        "  industry_l1 VARCHAR(50), industry_l2 VARCHAR(80), province VARCHAR(50), city VARCHAR(50),",
        "  scale_label VARCHAR(20), credit_level VARCHAR(10), credit_score NUMERIC(5,2),",
        "  tax_on_time_rate NUMERIC(5,4), tax_arrears_cnt INT, tax_violation_cnt INT, high_severity_cnt INT,",
        "  is_dishonesty BOOLEAN, is_execution BOOLEAN, loan_cnt INT, loan_amount NUMERIC(18,2),",
        "  vat_revenue NUMERIC(18,2), invoice_revenue NUMERIC(18,2), finance_revenue NUMERIC(18,2),",
        "  revenue_deviation NUMERIC(8,4), invoice_monthly_avg INT, invoice_cnt INT, red_invoice_cnt INT,",
        "  social_trend VARCHAR(10), social_months INT, profit_margin NUMERIC(10,4),",
        "  revenue_yoy NUMERIC(10,4), profit_yoy NUMERIC(10,4), debt_ratio NUMERIC(10,4),",
        "  cash_flow_net NUMERIC(18,2), cash_flow_level VARCHAR(10),",
        "  updated_at TIMESTAMPTZ DEFAULT now());",
        "CREATE TABLE IF NOT EXISTS legal_events (",
        "  id SERIAL PRIMARY KEY, enterprise_id VARCHAR(64) NOT NULL, event_type VARCHAR(30) NOT NULL,",
        "  severity CHAR(1) NOT NULL, amount_involved NUMERIC(18,2), event_date DATE,",
        "  description VARCHAR(200), source VARCHAR(30), created_at TIMESTAMPTZ DEFAULT now());",
        "DELETE FROM legal_events;",
        "DELETE FROM core_metrics;",
    ]
    col_list = ", ".join(CORE_COLUMNS)
    for c in companies:
        vals = ", ".join(_sql_literal(c[col]) for col in CORE_COLUMNS)
        lines.append(f"INSERT INTO core_metrics ({col_list}) VALUES ({vals});")
    for e in events:
        lines.append(
            f"INSERT INTO legal_events (id, enterprise_id, event_type, severity, amount_involved, "
            f"event_date, description, source, created_at) VALUES ("
            f"{e['id']},'{e['enterprise_id']}','{e['event_type']}','{e['severity']}',{e['amount_involved']},"
            f"'{e['event_date'].isoformat()}','{e['description']}','{e['source']}',NOW());"
        )
    lines.append(
        "SELECT setval(pg_get_serial_sequence('legal_events','id'), "
        "(SELECT COALESCE(MAX(id),1) FROM legal_events));"
    )
    return "\n".join(lines)


async def import_to_db(companies: list[dict], events: list[dict]) -> None:
    from sqlalchemy import delete, text

    from app.db.session import _get_async_session_local
    from app.models.core_metrics import CoreMetrics, LegalEvent
    from app.services import assessment

    async with _get_async_session_local() as db:
        await db.execute(delete(LegalEvent))
        await db.execute(delete(CoreMetrics))
        await db.flush()

        for c in companies:
            row = {k: v for k, v in c.items() if not k.startswith("_")}
            db.add(CoreMetrics(**row))
        for e in events:
            db.add(
                LegalEvent(
                    enterprise_id=e["enterprise_id"],
                    event_type=e["event_type"],
                    severity=e["severity"],
                    amount_involved=e["amount_involved"],
                    event_date=e["event_date"],
                    description=e["description"],
                    source=e["source"],
                )
            )
        await db.commit()

        assessment._CACHE["metrics"] = []
        assessment._CACHE["legal_by_ent"] = {}
        await assessment.refresh_cache(db)

        cnt = await db.scalar(text("SELECT COUNT(*) FROM core_metrics"))
        ev_cnt = await db.scalar(text("SELECT COUNT(*) FROM legal_events"))
        print(f"已导入 core_metrics: {cnt} 条, legal_events: {ev_cnt} 条")


async def main_async() -> None:
    companies = generate_companies()
    events = generate_legal_events(companies)

    base = Path(__file__).resolve().parent
    (base / "seed_data.sql").write_text(write_sql(companies, events), encoding="utf-8")
    # 清理遗留网络图死数据
    for dead in ("app/data/invoice_edges.json", "app/data/companies_registry.json"):
        p = base / dead
        if p.exists():
            p.unlink()
            print(f"已删除遗留文件 {dead}")

    print(
        f"seed_data.sql 已生成（{len(companies)} 家匿名标签企业, "
        f"{len(events)} 条法律事件）"
    )
    if os.getenv("SEED_IMPORT", "0") == "1":
        await import_to_db(companies, events)
    else:
        print("跳过 DB 导入（设置 SEED_IMPORT=1 可导入；有真实 ETL 数据时勿覆盖）")


if __name__ == "__main__":
    asyncio.run(main_async())
