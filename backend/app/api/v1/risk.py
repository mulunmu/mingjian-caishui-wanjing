import json
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.models.core_metrics import CoreMetrics
from app.models.financials import EnterpriseFinancials
from app.models.profiles import EnterpriseInvoiceProfile, EnterpriseTaxProfile
from app.services import assessment, mock_data
from app.services import fraud_engine, authenticity_engine, insight_engine
from app.services import financial_benchmarks
from app.services import subscription_service
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/risk", tags=["risk"])


def _f(v: Decimal | int | float | None) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _ratio_or_none(v: Decimal | int | float | None) -> float | None:
    """比率 0=弃权 → JSON null，禁止前端展示成「0%」。"""
    try:
        x = float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return None
    return None if x == 0.0 else x


def _amt_or_none(v: Decimal | int | float | None) -> float | None:
    """金额字段：仅 None 弃权；真实 0 元保留为 0.0。"""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _loads_json(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []


def _serialize_invoice_profile(p: EnterpriseInvoiceProfile | None) -> dict | None:
    if not p:
        return None
    return {
        "sales_invoice_cnt": p.sales_invoice_cnt,
        "purchase_invoice_cnt": p.purchase_invoice_cnt,
        "sales_amount": _f(p.sales_amount),
        "purchase_amount": _f(p.purchase_amount),
        "red_invoice_cnt": p.red_invoice_cnt,
        "void_invoice_cnt": p.void_invoice_cnt,
        "abnormal_invoice_cnt": p.abnormal_invoice_cnt,
        "category_count": p.category_count,
        "top_category_name": p.top_category_name or "",
        "top_category_share": _f(p.top_category_share),
        "top_categories": _loads_json(p.top_categories_json),
        "customer_count": p.customer_count,
        "top_customer_name": p.top_customer_name or "",
        "top_customer_share": _f(p.top_customer_share),
        "customer_hhi": _f(p.customer_hhi),
        "top_customers": _loads_json(p.top_customers_json),
        "supplier_count": p.supplier_count,
        "top_supplier_name": p.top_supplier_name or "",
        "top_supplier_share": _f(p.top_supplier_share),
        "supplier_hhi": _f(p.supplier_hhi),
        "top_suppliers": _loads_json(p.top_suppliers_json),
        "avg_unit_price": _f(p.avg_unit_price),
        "max_unit_price": _f(p.max_unit_price),
    }


def _serialize_tax_profile(p: EnterpriseTaxProfile | None) -> dict | None:
    if not p:
        return None
    return {
        "vat_sales_amount": _f(p.vat_sales_amount),
        "vat_payable": _f(p.vat_payable),
        "vat_burden": _ratio_or_none(p.vat_burden),
        "income_tax_payable": _f(p.income_tax_payable),
        "income_tax_burden": _ratio_or_none(p.income_tax_burden),
        "total_tax_paid": _f(p.total_tax_paid),
        "tax_late_penalty_amount": _f(p.tax_late_penalty_amount),
        "tax_late_penalty_cnt": p.tax_late_penalty_cnt,
        "correction_times": p.correction_times,
        "correction_records": p.correction_records,
        "correction_levy_count": p.correction_levy_count,
        "social_headcount": p.social_headcount,
        "social_insured_count": p.social_insured_count,
        "social_payment_base": _f(p.social_payment_base),
        "social_monthly_payment": _f(p.social_monthly_payment),
        "tax_loan_amount": _f(p.tax_loan_amount),
        "tax_loan_balance": _f(p.tax_loan_balance),
        "tax_loan_success_cnt": p.tax_loan_success_cnt,
        "tax_loan_apply_cnt": p.tax_loan_apply_cnt,
        "tax_loan_success_rate": _ratio_or_none(p.tax_loan_success_rate),
        "tax_preference_amount": _f(p.tax_preference_amount),
        "rd_expense": _f(p.rd_expense),
        "is_high_tech": bool(p.is_high_tech),
        "payroll_amount": _f(p.payroll_amount),
        "investor_cnt": p.investor_cnt,
        "top_investor_share": _ratio_or_none(p.top_investor_share),
        "change_cnt": p.change_cnt,
    }


def _serialize_financial(f: EnterpriseFinancials | None) -> dict | None:
    if not f:
        return None
    return {
        "report_year": f.report_year or "",
        "dupont": financial_benchmarks.dupont_breakdown(
            net_margin=f.net_margin,
            asset_turnover=f.asset_turnover,
            total_assets=f.total_assets,
            owner_equity=f.owner_equity,
            roe=f.roe,
        ),
        "balance_sheet": {
            "total_assets": _amt_or_none(f.total_assets),
            "total_liab": _amt_or_none(f.total_liab),
            "current_assets": _amt_or_none(f.current_assets),
            "current_liab": _amt_or_none(f.current_liab),
            "cash_equiv": _amt_or_none(f.cash_equiv),
            "inventory": _amt_or_none(f.inventory),
            "accounts_receivable": _amt_or_none(f.accounts_receivable),
            "fixed_assets": _amt_or_none(f.fixed_assets),
            "short_loan": _amt_or_none(f.short_loan),
            "owner_equity": _amt_or_none(f.owner_equity),
            "retained_earnings": _amt_or_none(f.retained_earnings),
        },
        "income_statement": {
            "revenue": _amt_or_none(f.revenue),
            "cost": _amt_or_none(f.cost),
            "tax_surcharge": _amt_or_none(f.tax_surcharge),
            "sell_expense": _amt_or_none(f.sell_expense),
            "admin_expense": _amt_or_none(f.admin_expense),
            "finance_expense": _amt_or_none(f.finance_expense),
            "operating_profit": _amt_or_none(f.operating_profit),
            "total_profit": _amt_or_none(f.total_profit),
            "income_tax": _amt_or_none(f.income_tax),
            "net_profit": _amt_or_none(f.net_profit),
        },
        "cash_flow": {
            "operating_cf": _amt_or_none(f.operating_cf),
            "investing_cf": _amt_or_none(f.investing_cf),
            "financing_cf": _amt_or_none(f.financing_cf),
        },
        "ratios": {
            "current_ratio": _ratio_or_none(f.current_ratio),
            "quick_ratio": _ratio_or_none(f.quick_ratio),
            "debt_ratio": _ratio_or_none(f.debt_ratio),
            "receivables_turnover": _ratio_or_none(f.receivables_turnover),
            "inventory_turnover": _ratio_or_none(f.inventory_turnover),
            "asset_turnover": _ratio_or_none(f.asset_turnover),
            "gross_margin": _ratio_or_none(f.gross_margin),
            "net_margin": _ratio_or_none(f.net_margin),
            "roe": _ratio_or_none(f.roe),
            "roa": _ratio_or_none(f.roa),
            "revenue_yoy": _ratio_or_none(f.revenue_yoy),
            "profit_yoy": _ratio_or_none(f.profit_yoy),
        },
    }


@router.get("/warnings")
async def list_warnings(db: AsyncSession = Depends(get_db), _user: dict | None = Depends(get_current_user_optional)):
    """风控预警（活数据）；DB 不可用时返回 503，不伪造 mock。"""
    try:
        return await assessment.get_all_warnings(db)
    except Exception as exc:
        logger.warning("DB unavailable for /warnings: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="风控数据暂不可用，请稍后重试。演示数据不会在服务端伪造返回。",
        ) from exc


@router.get("/mock/sample")
async def mock_sample_bundle(_user: dict | None = Depends(get_current_user_optional)):
    """演示/mock 模式统一样机包（与 mock_data.py 同源）。"""
    return mock_data.get_mock_sample_bundle()


@router.get("/summary")
async def dashboard_summary(
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    """工作台 KPI + 风险等级分布（活数据；DB 不可用时返回 503，不伪造 mock）。"""
    try:
        return await assessment.get_dashboard_summary(db)
    except Exception as exc:
        logger.warning("DB unavailable for /summary: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="风控数据暂不可用，请稍后重试。演示数据不会在服务端伪造返回。",
        ) from exc


@router.get("/industries")
async def list_industries(
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    """行业大类列表（含样本计数），供报告向导范围选择。"""
    try:
        rows = (await db.execute(select(CoreMetrics.industry_l1))).scalars().all()
    except Exception as exc:
        logger.warning("industries unavailable: %s", exc)
        rows = []
    counts: dict[str, int] = {}
    for r in rows:
        if r:
            counts[r] = counts.get(r, 0) + 1
    return {"items": [{"industry_l1": k, "n": v} for k, v in sorted(counts.items())]}


@router.get("/enterprises")
async def list_enterprises(
    q: str | None = Query(None, description="按「企业N」或行业/地区关键字过滤"),
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    """单企业通道：可串联的「企业N」清单（含行业/地区），供报告向导「指定企业」选择。"""
    try:
        rows = (
            await db.execute(
                select(
                    CoreMetrics.enterprise_id,
                    CoreMetrics.display_name,
                    CoreMetrics.display_label,
                    CoreMetrics.industry_l1,
                    CoreMetrics.province,
                ).order_by(CoreMetrics.enterprise_id)
            )
        ).all()
    except Exception as exc:
        logger.warning("enterprises unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="企业清单暂不可用，请稍后重试。") from exc

    items = [
        {
            "enterprise_id": r[0],
            "display_name": r[1] or r[2],
            "industry_l1": r[3],
            "province": r[4],
        }
        for r in rows
    ]
    if q:
        needle = q.strip()
        items = [
            it
            for it in items
            if needle in (it["display_name"] or "")
            or needle in (it["industry_l1"] or "")
            or needle in (it["province"] or "")
        ]
    return {"items": items, "total": len(items)}


@router.get("/fraud")
async def fraud_overview(
    industry: str | None = Query(None, description="行业大类，如 制造/批发零售"),
    limit: int = Query(40, ge=5, le=120),
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    """反欺诈行业/整体切片（确定性算法）。"""
    q = select(CoreMetrics.enterprise_id, CoreMetrics.display_label, CoreMetrics.industry_l1, CoreMetrics.display_name)
    if industry:
        q = q.where(CoreMetrics.industry_l1 == industry)
    q = q.limit(limit)
    rows = (await db.execute(q)).all()
    batch = [(r[0], r[1], r[2], r[3]) for r in rows]
    return await run_blocking(fraud_engine.analyze_metrics_batch, batch, max_n=limit)


@router.get("/fraud/demo")
async def fraud_demo(_user: dict | None = Depends(get_current_user_optional)):
    """验收：假发票进销错配样本。"""
    return fraud_engine.fake_mismatch_sample()


@router.get("/authenticity")
async def authenticity_overview(
    industry: str | None = Query(None, description="行业大类"),
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    """真实性：多口径交叉 + Benford。"""
    q = select(CoreMetrics)
    if industry:
        q = q.where(CoreMetrics.industry_l1 == industry)
    metrics = list((await db.execute(q)).scalars().all())
    return await run_blocking(
        authenticity_engine.analyze_authenticity_batch, metrics, industry_l1=industry
    )


@router.get("/authenticity/demo")
async def authenticity_demo(_user: dict | None = Depends(get_current_user_optional)):
    """验收：Benford 违例样本 + 自然对照。"""
    return {
        "violation_sample": authenticity_engine.fake_benford_violation_sample(),
        "natural_sample": authenticity_engine.natural_benford_sample(),
    }


@router.get("/enterprise/{enterprise_id}")
async def get_enterprise_profile(
    enterprise_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    """个体画像：六维评估 + 同业基准定位 + 洞察研判 + 发票/税务画像（脱敏，无明文企业名）。"""
    try:
        profile = await assessment.calculate(db, enterprise_id)
        if not profile:
            raise HTTPException(status_code=404, detail="未找到该匿名样本。")
        benchmark = await assessment.peer_benchmark(db, enterprise_id)
        metrics, features = await insight_engine.load_insight_inputs(db, enterprise_id)
        insights = insight_engine.evaluate_insights(metrics, features) if metrics else []

        invp = await db.get(EnterpriseInvoiceProfile, enterprise_id)
        taxp = await db.get(EnterpriseTaxProfile, enterprise_id)
        # 财务仅在确有完整三大报表时暴露（has_financial_statements=False 或缺失 → 弃权，不返回全零 stub）
        cm = await db.get(CoreMetrics, enterprise_id)
        fin = await db.get(EnterpriseFinancials, enterprise_id)
        if not (cm and cm.has_financial_statements):
            fin = None
        anomaly_signals = await subscription_service.build_enterprise_signals(db, enterprise_id)
        return {
            "profile": profile,
            "peer_benchmark": benchmark,
            "insights": insight_engine.insights_to_dict(insights),
            "invoice_profile": _serialize_invoice_profile(invp),
            "tax_profile": _serialize_tax_profile(taxp),
            "financial": _serialize_financial(fin),
            "anomaly_signals": anomaly_signals,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for /enterprise: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="风控数据暂不可用，请稍后重试。演示数据不会在服务端伪造返回。",
        ) from exc
