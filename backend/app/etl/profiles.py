"""ETL：发票画像 / 税务画像（一企业一行，脱敏）。

数据扩容 Phase 2（发票）+ Phase 3（税务）。源表行级 GROUP BY 一次拉取，
与 fraud_engine 的逐企业回源互补：这里产出结构化宽表供报告章节溯源展示。

铁律：比率分母绝对值 <= 1 置 0（弃权）；文本列一律 U() 修复双重 UTF-8 乱码；
金额单位元；集中度/占比/税负率 0-1 浮点。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from app.db.mysql import U, fetch_all
from app.models.profiles import EnterpriseInvoiceProfile, EnterpriseTaxProfile
from app.services.enterprise_id import enterprise_id_of


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _ratio(num: float, den: float, lo: float, hi: float) -> float:
    if abs(den) <= 1.0:
        return 0.0
    return max(lo, min(hi, num / den))


def _topn_aggregate(rows: list[dict], name_key: str, taxno_key: str) -> dict:
    """把 (name, taxno, amt) 行聚合成 TOP1 占比 / HHI / TOP5 JSON。

    按 (taxno or name) 去重合并金额（同一对手方多张发票），金额降序取 TOP5。
    """
    agg: dict[str, dict] = {}
    for r in rows:
        name = (r.get(name_key) or "").strip()
        taxno = (r.get(taxno_key) or "").strip()
        amt = _f(r.get("amt"))
        key = taxno or name
        if not key:
            continue
        bucket = agg.setdefault(key, {"name": name, "taxno": taxno, "amount": 0.0})
        bucket["amount"] += amt
        if name and not bucket["name"]:
            bucket["name"] = name
    items = sorted(agg.values(), key=lambda x: -x["amount"])
    total = sum(x["amount"] for x in items)
    if total <= 1.0 or not items:
        return {
            "count": len(items),
            "top1_name": "",
            "top1_share": 0.0,
            "hhi": 0.0,
            "top5_json": json.dumps([], ensure_ascii=False),
        }
    shares = [x["amount"] / total for x in items]
    hhi = sum(s * s for s in shares)
    top1 = items[0]
    top5 = [
        {
            "name": x["name"] or x["taxno"],
            "taxno": x["taxno"],
            "amount": round(x["amount"], 2),
            "share": round(shares[i], 4),
        }
        for i, x in enumerate(items[:5])
    ]
    return {
        "count": len(items),
        "top1_name": top1["name"] or top1["taxno"],
        "top1_share": shares[0],
        "hhi": hhi,
        "top5_json": json.dumps(top5, ensure_ascii=False),
    }


def _category_aggregate(rows: list[dict], scbm4_to_name: dict[str, str]) -> dict:
    """品目（scbm4）聚合成 TOP1 占比 / HHI / TOP5（附商品名）。"""
    total = sum(_f(r.get("amt")) for r in rows)
    if total <= 1.0:
        return {
            "count": 0,
            "top1_name": "",
            "top1_share": 0.0,
            "hhi": 0.0,
            "top5_json": json.dumps([], ensure_ascii=False),
        }
    items = sorted(rows, key=lambda r: -_f(r.get("amt")))
    shares = [_f(r.get("amt")) / total for r in items]
    hhi = sum(s * s for s in shares)
    top1_scbm = (items[0].get("scbm4") or "") if items else ""
    top5 = [
        {
            "name": scbm4_to_name.get((r.get("scbm4") or ""), (r.get("scbm4") or "")),
            "amount": round(_f(r.get("amt")), 2),
            "share": round(shares[i], 4),
        }
        for i, r in enumerate(items[:5])
    ]
    return {
        "count": len(items),
        "top1_name": scbm4_to_name.get(top1_scbm, top1_scbm),
        "top1_share": shares[0] if shares else 0.0,
        "hhi": hhi,
        "top5_json": json.dumps(top5, ensure_ascii=False),
    }


def load_invoice_profile() -> dict[str, dict]:
    """发票画像：进销项、品目、客户/供应商集中度、单价、红字/作废/异常。"""
    # 1) 进销项规模 + 红字/作废/异常凭证（state: 1=作废 2=红冲）
    base_rows = fetch_all(
        f"""
        SELECT taxpayer_id,
               SUM(CASE WHEN {U('sign')} LIKE '%%销%%' THEN 1 ELSE 0 END) AS sales_cnt,
               SUM(CASE WHEN {U('sign')} LIKE '%%进%%' THEN 1 ELSE 0 END) AS purchase_cnt,
               SUM(CASE WHEN {U('sign')} LIKE '%%销%%' THEN COALESCE(CAST(NULLIF(hjje,'') AS DECIMAL(20,4)),0) ELSE 0 END) AS sales_amt,
               SUM(CASE WHEN {U('sign')} LIKE '%%进%%' THEN COALESCE(CAST(NULLIF(hjje,'') AS DECIMAL(20,4)),0) ELSE 0 END) AS purchase_amt,
               SUM(CASE WHEN state = 2 THEN 1 ELSE 0 END) AS red_cnt,
               SUM(CASE WHEN state = 1 THEN 1 ELSE 0 END) AS void_cnt,
               SUM(CASE WHEN {U('risk_level')} LIKE '%%异常%%' THEN 1 ELSE 0 END) AS abnormal_cnt
        FROM syx_invoice
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        GROUP BY taxpayer_id
        """
    )
    base = {enterprise_id_of(r["taxpayer_id"]): r for r in base_rows}

    # 2) 客户集中度（销项 → 购方）
    cust_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('gfmc')} AS gfmc, {U('gfsh')} AS gfsh,
               SUM(COALESCE(CAST(NULLIF(hjje,'') AS DECIMAL(20,4)),0)) AS amt
        FROM syx_invoice
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
          AND {U('sign')} LIKE '%%销%%'
          AND (zfbz IS NULL OR LOWER(zfbz) IN ('','n','0','false','否'))
        GROUP BY taxpayer_id, {U('gfmc')}, {U('gfsh')}
        """
    )
    cust_by_eid: dict[str, list[dict]] = defaultdict(list)
    for r in cust_rows:
        cust_by_eid[enterprise_id_of(r["taxpayer_id"])].append(r)

    # 3) 供应商集中度（进项 → 销方）
    supp_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('xfmc')} AS xfmc, {U('xfsh')} AS xfsh,
               SUM(COALESCE(CAST(NULLIF(hjje,'') AS DECIMAL(20,4)),0)) AS amt
        FROM syx_invoice
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
          AND {U('sign')} LIKE '%%进%%'
          AND (zfbz IS NULL OR LOWER(zfbz) IN ('','n','0','false','否'))
        GROUP BY taxpayer_id, {U('xfmc')}, {U('xfsh')}
        """
    )
    supp_by_eid: dict[str, list[dict]] = defaultdict(list)
    for r in supp_rows:
        supp_by_eid[enterprise_id_of(r["taxpayer_id"])].append(r)

    # 4a) 品目结构（scbm4 分类编码前4位）
    cat_rows = fetch_all(
        f"""
        SELECT taxpayer_id, LEFT(scbm, 4) AS scbm4, SUM(COALESCE(je,0)) AS amt
        FROM syx_invoice_details
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
          AND scbm IS NOT NULL AND scbm <> ''
        GROUP BY taxpayer_id, LEFT(scbm, 4)
        """
    )
    cat_by_eid: dict[str, list[dict]] = defaultdict(list)
    for r in cat_rows:
        cat_by_eid[enterprise_id_of(r["taxpayer_id"])].append(r)

    # 4b) scbm4 → 代表商品名（全局按金额取众数）
    name_rows = fetch_all(
        f"""
        SELECT LEFT(scbm, 4) AS scbm4, {U('spmc')} AS spmc, SUM(COALESCE(je,0)) AS amt
        FROM syx_invoice_details
        WHERE scbm IS NOT NULL AND scbm <> '' AND spmc IS NOT NULL AND spmc <> ''
        GROUP BY LEFT(scbm, 4), {U('spmc')}
        """
    )
    scbm4_name: dict[str, str] = {}
    scbm4_best: dict[str, float] = {}
    for r in name_rows:
        k = (r.get("scbm4") or "").strip()
        amt = _f(r.get("amt"))
        if amt > scbm4_best.get(k, -1.0):
            scbm4_best[k] = amt
            scbm4_name[k] = (r.get("spmc") or "").strip()

    # 5) 单价（销项明细：金额/数量 加权均价 + 最高不含税单价）
    price_rows = fetch_all(
        f"""
        SELECT taxpayer_id,
               SUM(COALESCE(je,0)) AS total_amt,
               SUM(COALESCE(spsl,0)) AS total_qty,
               MAX(COALESCE(bw_spdj,0)) AS max_price
        FROM syx_invoice_details
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
          AND spsl IS NOT NULL AND spsl <> '' AND CAST(spsl AS DECIMAL(20,4)) > 0
        GROUP BY taxpayer_id
        """
    )
    price = {enterprise_id_of(r["taxpayer_id"]): r for r in price_rows}

    out: dict[str, dict] = {}
    for eid, b in base.items():
        c = _topn_aggregate(cust_by_eid.get(eid, []), "gfmc", "gfsh")
        s = _topn_aggregate(supp_by_eid.get(eid, []), "xfmc", "xfsh")
        cat = _category_aggregate(cat_by_eid.get(eid, []), scbm4_name)
        p = price.get(eid, {})
        total_qty = _f(p.get("total_qty"))
        total_amt = _f(p.get("total_amt"))
        avg_price = total_amt / total_qty if total_qty > 0 else 0.0
        out[eid] = {
            "sales_invoice_cnt": int(_f(b.get("sales_cnt"))),
            "purchase_invoice_cnt": int(_f(b.get("purchase_cnt"))),
            "sales_amount": _f(b.get("sales_amt")),
            "purchase_amount": _f(b.get("purchase_amt")),
            "red_invoice_cnt": int(_f(b.get("red_cnt"))),
            "void_invoice_cnt": int(_f(b.get("void_cnt"))),
            "abnormal_invoice_cnt": int(_f(b.get("abnormal_cnt"))),
            "category_count": cat["count"],
            "top_category_name": (cat["top1_name"] or "")[:120],
            "top_category_share": cat["top1_share"],
            "top_categories_json": cat["top5_json"],
            "customer_count": c["count"],
            "top_customer_name": (c["top1_name"] or "")[:120],
            "top_customer_share": c["top1_share"],
            "customer_hhi": c["hhi"],
            "top_customers_json": c["top5_json"],
            "supplier_count": s["count"],
            "top_supplier_name": (s["top1_name"] or "")[:120],
            "top_supplier_share": s["top1_share"],
            "supplier_hhi": s["hhi"],
            "top_suppliers_json": s["top5_json"],
            "avg_unit_price": round(avg_price, 4),
            "max_unit_price": _f(p.get("max_price")),
        }
    return out


def _norm_line(name: str) -> str:
    """归一化申报表行项目名用于精确匹配（去序号/加/减/其中前缀/括号/非汉字）。"""
    n = (name or "").strip()
    n = re.sub(r"^[一二三四五六七八九十]+、", "", n)
    n = re.sub(r"^(加|减|其中)[：:]", "", n)
    n = re.sub(r"^[（(].*?[）)]", "", n)  # 去行首括号序号如「(一)」「(四)」
    n = re.sub(r"[（(].*?[）)]", "", n)
    return re.sub(r"[^一-鿿]", "", n)


def _line_max(rows: list[dict], keys: set[str], value_key: str) -> float:
    """取行项目名精确命中 keys 的最大金额（latest cumulative）。"""
    best = 0.0
    for r in rows:
        if _norm_line(r.get("project_name") or "") in keys:
            v = _f(r.get(value_key))
            if v > best:
                best = v
    return best


def load_tax_profile() -> dict[str, dict]:
    """税务画像：税负率、完税诚信、申报更正、社保、银税互动、优惠/研发/股权。"""
    # 增值税金额表达式：与 load_vat_revenue 对齐（本年累计 + 货物/服务累计）
    VAT_AMT = (
        "COALESCE(general_year_accumulative_amount,0)"
        " + COALESCE(current_year_accumulative_goods,0)"
        " + COALESCE(current_year_accumulative_service,0)"
    )
    # 1) 增值税：销售额 + 应纳税额合计
    vat_sales_rows = fetch_all(
        f"""
        SELECT taxpayer_id, MAX({VAT_AMT}) AS v
        FROM syx_tax_value_added
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
          AND {U('project_name')} LIKE '%%销售额%%'
        GROUP BY taxpayer_id
        """
    )
    vat_payable_rows = fetch_all(
        f"""
        SELECT taxpayer_id, MAX({VAT_AMT}) AS v
        FROM syx_tax_value_added
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
          AND {U('project_name')} LIKE '%%应纳税额合计%%'
        GROUP BY taxpayer_id
        """
    )
    vat_sales = {enterprise_id_of(r["taxpayer_id"]): _f(r.get("v")) for r in vat_sales_rows}
    vat_payable = {enterprise_id_of(r["taxpayer_id"]): _f(r.get("v")) for r in vat_payable_rows}

    # 2) 企业所得税：应纳所得税额 / 营业收入
    cit_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('project_name')} AS project_name, amount
        FROM syx_corporate_income_year
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        """
    )
    cit_by_eid: dict[str, list[dict]] = defaultdict(list)
    for r in cit_rows:
        cit_by_eid[enterprise_id_of(r["taxpayer_id"])].append(r)
    INCOME_TAX_KEYS = {"应纳所得税额", "应纳税额"}
    INCOME_REV_KEYS = {"营业收入"}

    # 3) 完税：已缴税款 / 滞纳金罚款
    paid_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('tax_type')} AS tax_type, {U('tax_attributes')} AS tax_attributes,
               SUM(COALESCE(tax_paid,0)) AS paid, COUNT(*) AS cnt
        FROM syx_tax_payment
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        GROUP BY taxpayer_id, {U('tax_type')}, {U('tax_attributes')}
        """
    )
    paid_by_eid: dict[str, dict] = {}
    for r in paid_rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        d = paid_by_eid.setdefault(eid, {"total_paid": 0.0, "late_amt": 0.0, "late_cnt": 0})
        typ = (r.get("tax_type") or "") + (r.get("tax_attributes") or "")
        paid = _f(r.get("paid"))
        if ("滞纳" in typ) or ("罚款" in typ) or ("行为罚" in typ):
            d["late_amt"] += paid
            d["late_cnt"] += int(_f(r.get("cnt")))
        else:
            d["total_paid"] += paid

    # 4) 申报更正（总更正次数 = 各申报 already_change_times 累加；单次最多更正记 max_times）
    corr_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('levy_project_name')} AS levy,
               MAX(already_change_times) AS max_times,
               SUM(COALESCE(already_change_times,0)) AS sum_times,
               COUNT(*) AS rec_cnt
        FROM syx_declaration_correction
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        GROUP BY taxpayer_id, {U('levy_project_name')}
        """
    )
    corr_by_eid: dict[str, dict] = {}
    for r in corr_rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        d = corr_by_eid.setdefault(eid, {"sum_times": 0, "rec_cnt": 0, "levy": set()})
        d["sum_times"] += int(_f(r.get("sum_times")))
        d["rec_cnt"] += int(_f(r.get("rec_cnt")))
        d["levy"].add(r.get("levy") or "")

    # 5) 社保：缴费人数 / 参保人数 / 缴费基数 / 月均应缴
    social_rows = fetch_all(
        f"""
        SELECT taxpayer_id, MAX(payment_people_number) AS headcount,
               MAX(enrollment_number) AS insured,
               MAX(payment_base) AS base,
               SUM(COALESCE(payment_amount, should_payment_amount, 0)) AS total_pay,
               COUNT(DISTINCT DATE_FORMAT(begin_date, '%%Y-%%m')) AS months
        FROM syx_social_declaration
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        GROUP BY taxpayer_id
        """
    )
    social = {enterprise_id_of(r["taxpayer_id"]): r for r in social_rows}

    # 6) 银税互动融资
    loan_rows = fetch_all(
        f"""
        SELECT taxpayer_id,
               SUM(COALESCE(loan_amount,0)) AS loan_amt,
               SUM(COALESCE(loan_balance,0)) AS loan_bal,
               COUNT(*) AS apply_cnt,
               SUM(CASE WHEN {U('status')} IN ('授信成功','授权成功','有效') THEN 1 ELSE 0 END) AS success_cnt
        FROM syx_tax_interaction
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        GROUP BY taxpayer_id
        """
    )
    loan = {enterprise_id_of(r["taxpayer_id"]): r for r in loan_rows}

    # 7) 优惠 / 研发 / 高新 / 职工薪酬（汇算清缴附表）
    pref_rows = fetch_all(
        """
        SELECT taxpayer_id, SUM(COALESCE(amount,0)) AS v FROM syx_corporate_income_year_jmsds
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> '' GROUP BY taxpayer_id
        """
    )
    rd_rows = fetch_all(
        """
        SELECT taxpayer_id, SUM(COALESCE(amount,0)) AS v FROM syx_corporate_income_year_yffy
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> '' GROUP BY taxpayer_id
        """
    )
    gxjs_rows = fetch_all(
        """
        SELECT DISTINCT taxpayer_id FROM syx_corporate_income_year_gxjs
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        """
    )
    payroll_rows = fetch_all(
        f"""
        SELECT taxpayer_id, {U('project_name')} AS project_name, zzje, sjfse
        FROM syx_corporate_income_year_zgxc
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        """
    )
    pref = {enterprise_id_of(r["taxpayer_id"]): _f(r["v"]) for r in pref_rows}
    rd = {enterprise_id_of(r["taxpayer_id"]): _f(r["v"]) for r in rd_rows}
    hightech = {enterprise_id_of(r["taxpayer_id"]) for r in gxjs_rows}
    payroll: dict[str, float] = {}
    for r in payroll_rows:
        eid = enterprise_id_of(r["taxpayer_id"])
        line = _norm_line(r.get("project_name") or "")
        # 取「合计」行账载金额；若无则累加账载金额
        if line in {"合计", "职工薪酬", "工资薪金支出"}:
            payroll[eid] = max(payroll.get(eid, 0.0), _f(r.get("zzje")))

    # 8) 股权：投资方 + 第一大比例
    investor_rows = fetch_all(
        f"""
        SELECT taxpayer_id, COUNT(*) AS cnt, MAX(CAST(tzbl AS DECIMAL(10,4))) AS top_share
        FROM syx_investor_info
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> ''
        GROUP BY taxpayer_id
        """
    )
    investor = {enterprise_id_of(r["taxpayer_id"]): r for r in investor_rows}

    # 9) 变更登记次数
    change_rows = fetch_all(
        """
        SELECT taxpayer_id, COUNT(*) AS cnt FROM syx_enterprise_change_info
        WHERE taxpayer_id IS NOT NULL AND taxpayer_id <> '' GROUP BY taxpayer_id
        """
    )
    change = {enterprise_id_of(r["taxpayer_id"]): int(_f(r["cnt"])) for r in change_rows}

    out: dict[str, dict] = {}
    all_eids = (
        set(vat_sales) | set(vat_payable) | set(cit_by_eid) | set(paid_by_eid)
        | set(corr_by_eid) | set(social) | set(loan) | set(pref) | set(rd)
        | set(hightech) | set(payroll) | set(investor) | set(change)
    )
    for eid in all_eids:
        sales = vat_sales.get(eid, 0.0)
        payable_vat = vat_payable.get(eid, 0.0)
        income_tax = _line_max(cit_by_eid.get(eid, []), INCOME_TAX_KEYS, "amount")
        income_rev = _line_max(cit_by_eid.get(eid, []), INCOME_REV_KEYS, "amount")
        pd = paid_by_eid.get(eid, {})
        cr = corr_by_eid.get(eid, {})
        soc = social.get(eid, {})
        ln = loan.get(eid, {})
        iv = investor.get(eid, {})
        apply_cnt = int(_f(ln.get("apply_cnt")))
        success_cnt = int(_f(ln.get("success_cnt")))
        out[eid] = {
            "vat_sales_amount": sales,
            "vat_payable": payable_vat,
            "vat_burden": _ratio(payable_vat, sales, 0.0, 1.0),
            "income_tax_payable": income_tax,
            "income_tax_burden": _ratio(income_tax, income_rev, 0.0, 1.0),
            "total_tax_paid": pd.get("total_paid", 0.0),
            "tax_late_penalty_amount": pd.get("late_amt", 0.0),
            "tax_late_penalty_cnt": pd.get("late_cnt", 0),
            "correction_times": int(cr.get("sum_times", 0)),  # 口径=各申报 already_change_times 求和
            "correction_records": cr.get("rec_cnt", 0),
            "correction_levy_count": len(cr.get("levy", set())),
            "social_headcount": int(_f(soc.get("headcount"))),
            "social_insured_count": int(_f(soc.get("insured"))),
            "social_payment_base": _f(soc.get("base")),
            "social_monthly_payment": _f(soc.get("total_pay")) / max(int(_f(soc.get("months"))), 1),
            "tax_loan_amount": _f(ln.get("loan_amt")),
            "tax_loan_balance": _f(ln.get("loan_bal")),
            "tax_loan_success_cnt": success_cnt,
            "tax_loan_apply_cnt": apply_cnt,
            "tax_loan_success_rate": _ratio(success_cnt, apply_cnt, 0.0, 1.0),
            "tax_preference_amount": pref.get(eid, 0.0),
            "rd_expense": rd.get(eid, 0.0),
            "is_high_tech": eid in hightech,
            "payroll_amount": payroll.get(eid, 0.0),
            "investor_cnt": int(_f(iv.get("cnt"))),
            "top_investor_share": min(1.0, max(0.0, _f(iv.get("top_share")) / 100.0)),  # tzbl 百分比 → 0-1
            "change_cnt": change.get(eid, 0),
        }
    return out


def build_invoice_profiles(ents: dict[str, dict], data: dict[str, dict]) -> list[EnterpriseInvoiceProfile]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    rows: list[EnterpriseInvoiceProfile] = []
    for eid in ents:
        d = data.get(eid, {})
        rows.append(
            EnterpriseInvoiceProfile(
                enterprise_id=eid,
                sales_invoice_cnt=int(d.get("sales_invoice_cnt", 0)),
                purchase_invoice_cnt=int(d.get("purchase_invoice_cnt", 0)),
                sales_amount=float(d.get("sales_amount", 0)),
                purchase_amount=float(d.get("purchase_amount", 0)),
                red_invoice_cnt=int(d.get("red_invoice_cnt", 0)),
                void_invoice_cnt=int(d.get("void_invoice_cnt", 0)),
                abnormal_invoice_cnt=int(d.get("abnormal_invoice_cnt", 0)),
                category_count=int(d.get("category_count", 0)),
                top_category_name=d.get("top_category_name", ""),
                top_category_share=float(d.get("top_category_share", 0)),
                top_categories_json=d.get("top_categories_json"),
                customer_count=int(d.get("customer_count", 0)),
                top_customer_name=d.get("top_customer_name", ""),
                top_customer_share=float(d.get("top_customer_share", 0)),
                customer_hhi=float(d.get("customer_hhi", 0)),
                top_customers_json=d.get("top_customers_json"),
                supplier_count=int(d.get("supplier_count", 0)),
                top_supplier_name=d.get("top_supplier_name", ""),
                top_supplier_share=float(d.get("top_supplier_share", 0)),
                supplier_hhi=float(d.get("supplier_hhi", 0)),
                top_suppliers_json=d.get("top_suppliers_json"),
                avg_unit_price=float(d.get("avg_unit_price", 0)),
                max_unit_price=float(d.get("max_unit_price", 0)),
                updated_at=now,
            )
        )
    return rows


def build_tax_profiles(ents: dict[str, dict], data: dict[str, dict]) -> list[EnterpriseTaxProfile]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    rows: list[EnterpriseTaxProfile] = []
    for eid in ents:
        d = data.get(eid, {})
        rows.append(
            EnterpriseTaxProfile(
                enterprise_id=eid,
                vat_sales_amount=float(d.get("vat_sales_amount", 0)),
                vat_payable=float(d.get("vat_payable", 0)),
                vat_burden=float(d.get("vat_burden", 0)),
                income_tax_payable=float(d.get("income_tax_payable", 0)),
                income_tax_burden=float(d.get("income_tax_burden", 0)),
                total_tax_paid=float(d.get("total_tax_paid", 0)),
                tax_late_penalty_amount=float(d.get("tax_late_penalty_amount", 0)),
                tax_late_penalty_cnt=int(d.get("tax_late_penalty_cnt", 0)),
                correction_times=int(d.get("correction_times", 0)),
                correction_records=int(d.get("correction_records", 0)),
                correction_levy_count=int(d.get("correction_levy_count", 0)),
                social_headcount=int(d.get("social_headcount", 0)),
                social_insured_count=int(d.get("social_insured_count", 0)),
                social_payment_base=float(d.get("social_payment_base", 0)),
                social_monthly_payment=float(d.get("social_monthly_payment", 0)),
                tax_loan_amount=float(d.get("tax_loan_amount", 0)),
                tax_loan_balance=float(d.get("tax_loan_balance", 0)),
                tax_loan_success_cnt=int(d.get("tax_loan_success_cnt", 0)),
                tax_loan_apply_cnt=int(d.get("tax_loan_apply_cnt", 0)),
                tax_loan_success_rate=float(d.get("tax_loan_success_rate", 0)),
                tax_preference_amount=float(d.get("tax_preference_amount", 0)),
                rd_expense=float(d.get("rd_expense", 0)),
                is_high_tech=bool(d.get("is_high_tech", False)),
                payroll_amount=float(d.get("payroll_amount", 0)),
                investor_cnt=int(d.get("investor_cnt", 0)),
                top_investor_share=float(d.get("top_investor_share", 0)),
                change_cnt=int(d.get("change_cnt", 0)),
                updated_at=now,
            )
        )
    return rows
