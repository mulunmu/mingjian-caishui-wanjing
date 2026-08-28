import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.models.core_metrics import CoreMetrics
from app.services import assessment, mock_data
from app.services import fraud_engine, authenticity_engine
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/risk", tags=["risk"])


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


@router.get("/fraud")
async def fraud_overview(
    industry: str | None = Query(None, description="行业大类，如 制造/批发零售"),
    limit: int = Query(40, ge=5, le=120),
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    """反欺诈行业/整体切片（确定性算法）。"""
    q = select(CoreMetrics.enterprise_id, CoreMetrics.display_label, CoreMetrics.industry_l1)
    if industry:
        q = q.where(CoreMetrics.industry_l1 == industry)
    q = q.limit(limit)
    rows = (await db.execute(q)).all()
    batch = [(r[0], r[1], r[2]) for r in rows]
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
    """个体画像：五维评估 + 同业基准定位（脱敏，无明文企业名）。"""
    try:
        profile = await assessment.calculate(db, enterprise_id)
        if not profile:
            raise HTTPException(status_code=404, detail="未找到该匿名样本。")
        benchmark = await assessment.peer_benchmark(db, enterprise_id)
        return {
            "profile": profile,
            "peer_benchmark": benchmark,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for /enterprise: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="风控数据暂不可用，请稍后重试。演示数据不会在服务端伪造返回。",
        ) from exc
