"""数据接入 API（阶段二）——口径统一 + 临时/永久决策。

本切片落地「字段映射 + 写决策」骨架：
- /ingest/map    ：表头 → 四层字段映射建议（复用已存口径，LLM 兜底，只发表头元数据）
- /ingest/commit ：用户确认映射 + 选择「临时（会话内）/ 永久（沉淀为已存口径）」

行级数据 ETL（解析 Excel/CSV → 写入 core_metrics）为后续切片，本接口不伪称已写入原始数据。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.metric_registry import FieldMapping
from app.services import field_mapping, ingest as ingest_service
from app.services.metric_registry import SOURCE_FIELDS
from app.services.session_store import ensure_session_id, store as session_store
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])

VALID_TARGETS = {sf["field"] for sf in SOURCE_FIELDS}


class IngestMapRequest(BaseModel):
    columns: list[str] = Field(min_length=1, max_length=200)
    use_llm: bool = True


class MappingConfirm(BaseModel):
    source_column: str
    target_field: str | None = None


class IngestCommitRequest(BaseModel):
    mappings: list[MappingConfirm] = Field(min_length=1, max_length=500)
    mode: str = "temporary"  # temporary | permanent
    session_id: str | None = None


class IngestRowsRequest(BaseModel):
    session_id: str | None = None
    identity_field: str | None = Field(None, description="唯一键列名（税号/企业名/统一编号），明文不落库")
    mappings: list[MappingConfirm] = Field(min_length=1, max_length=500)
    rows: list[dict] = Field(min_length=1, max_length=5000)
    mode: str = "temporary"  # temporary | permanent


async def _load_saved(db: AsyncSession) -> dict[str, str]:
    """加载已存映射（saved 层）：归一化别名 → 目标字段。"""
    saved: dict[str, str] = {}
    try:
        rows = (await db.execute(select(FieldMapping))).scalars().all()
        for r in rows:
            saved[field_mapping.normalize(r.source_alias)] = r.target_field
    except Exception as exc:
        logger.debug("load saved field mappings failed: %s", exc)
    return saved


@router.post("/map")
async def map_columns_endpoint(
    body: IngestMapRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_roles("admin")),
):
    """表头列名 → 字段映射建议（saved→exact→fuzzy→LLM）。"""
    saved = await _load_saved(db)
    if body.use_llm:
        mappings = await field_mapping.map_columns_with_llm(body.columns, saved)
    else:
        mappings = field_mapping.map_columns(body.columns, saved)
    matched = sum(1 for m in mappings if m["target_field"])
    return {"mappings": mappings, "matched": matched, "total": len(mappings)}


@router.post("/commit")
async def commit_ingest(
    body: IngestCommitRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_roles("admin")),
):
    """确认字段映射 + 写决策。

    - temporary：会话内临时（TTL 30min），仅本次分析可用。
    - permanent：确认的映射沉淀为「已存口径」，后续上传同名列免 LLM 直接命中。
    """
    if body.mode not in ("temporary", "permanent"):
        raise HTTPException(status_code=400, detail="mode 只能是 temporary 或 permanent")

    confirmed = []
    for m in body.mappings:
        tgt = m.target_field
        if tgt is None:
            continue
        if tgt not in VALID_TARGETS:
            raise HTTPException(status_code=400, detail=f"未知目标字段：{tgt}")
        confirmed.append({"source_column": m.source_column, "target_field": tgt})

    if not confirmed:
        raise HTTPException(status_code=400, detail="至少一条有效映射")

    if body.mode == "temporary":
        sid = await run_blocking(ensure_session_id, body.session_id)
        session_store[sid]["pending_ingest"] = {"mappings": confirmed, "mode": "temporary"}
        return {"mode": "temporary", "session_id": sid, "accepted": len(confirmed)}

    # permanent：upsert 到已存映射表（saved 层）
    saved_count = 0
    try:
        for m in confirmed:
            key = field_mapping.normalize(m["source_column"])
            existing = (
                await db.execute(
                    select(FieldMapping).where(
                        FieldMapping.source_alias == m["source_column"],
                        FieldMapping.target_field == m["target_field"],
                    )
                )
            ).scalars().first()
            if existing is None:
                db.add(
                    FieldMapping(
                        source_alias=m["source_column"],
                        target_field=m["target_field"],
                        confidence=100,
                        origin="manual",
                    )
                )
                saved_count += 1
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("commit permanent field mappings failed: %s", exc)
        raise HTTPException(status_code=503, detail="已存口径写入失败，请稍后重试。") from exc

    return {"mode": "permanent", "saved_count": saved_count, "accepted": len(confirmed)}


@router.post("/rows")
async def ingest_rows(
    body: IngestRowsRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_roles("admin")),
):
    """行级数据写入：映射 + 强转 + 身份 MD5 派生。

    - temporary：会话内暂存（TTL 30min），不落 core_metrics。
    - permanent：写入 core_metrics（身份仅 MD5，display_label 匿名）。
    响应只回 hashed enterprise_id + 匿名标签，绝不回显明文身份。
    """
    if body.mode not in ("temporary", "permanent"):
        raise HTTPException(status_code=400, detail="mode 只能是 temporary 或 permanent")

    mappings: dict[str, str] = {}
    for m in body.mappings:
        if m.target_field is None:
            continue
        if m.target_field not in VALID_TARGETS:
            raise HTTPException(status_code=400, detail=f"未知目标字段：{m.target_field}")
        mappings[m.source_column] = m.target_field

    ingested, errors = ingest_service.process_ingest_rows(
        body.rows, mappings, body.identity_field
    )
    anonymized = [
        {"enterprise_id": it["enterprise_id"], "display_label": it["display_label"]}
        for it in ingested
    ]

    if body.mode == "temporary":
        sid = await run_blocking(ensure_session_id, body.session_id)
        session_store[sid]["pending_rows"] = ingested
        return {
            "mode": "temporary",
            "session_id": sid,
            "ingested": len(ingested),
            "errors": errors,
            "enterprises": anonymized,
        }

    # permanent：写 core_metrics（upsert）
    try:
        from sqlalchemy import select

        from app.models.core_metrics import CoreMetrics

        # 计算下一个可读名「企业N」：取已有 display_name 最大数值后缀 +1，保证新增企业不重名
        max_n = 0
        for name in (
            await db.execute(select(CoreMetrics.display_name).where(CoreMetrics.display_name.isnot(None)))
        ).scalars().all():
            if name and name.startswith("企业"):
                try:
                    max_n = max(max_n, int(name[2:]))
                except ValueError:
                    pass

        for it in ingested:
            kwargs = ingest_service.to_core_metrics_kwargs(it)
            eid = kwargs.pop("enterprise_id")
            existing = await db.get(CoreMetrics, eid)
            if existing is None:
                max_n += 1
                db.add(CoreMetrics(enterprise_id=eid, display_name=f"企业{max_n}", **kwargs))
            else:
                for k, v in kwargs.items():
                    setattr(existing, k, v)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("permanent row ingest failed: %s", exc)
        raise HTTPException(status_code=503, detail="数据写入失败，请稍后重试。") from exc

    try:
        from app.services.assessment import refresh_cache

        await refresh_cache(db)
    except Exception as exc:
        logger.warning("assessment cache refresh after ingest failed: %s", exc)

    return {
        "mode": "permanent",
        "ingested": len(ingested),
        "errors": errors,
        "enterprises": anonymized,
    }
