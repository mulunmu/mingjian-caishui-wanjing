import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional, require_plan
from app.db.session import get_db
from app.services import auth_service, email_service, slice_report
from app.services.report_templates import PremiumReportLocked, get_scenario_label
from app.services.slice_report import (
    can_access_report,
    cleanup_legacy_reports,
    generate_slice_report,
    get_report_path,
    preview_slice_report_html,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/report", tags=["report"])


def _premium_locked() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail="定制报告为付费功能，开发期已隔离，当前仅提供通用模板。",
    )


class GenerateReportRequest(BaseModel):
    enterprise_id: str | None = None
    scenario: str = "general"
    session_id: str | None = None
    query: str | None = None


class GenerateSliceReportRequest(BaseModel):
    scenario: str | None = None
    session_id: str | None = None
    query: str | None = None


class GenerateEnterpriseReportRequest(BaseModel):
    enterprise_id: str


class EmailReportRequest(BaseModel):
    enterprise_id: str | None = None
    recipient: EmailStr
    scenario: str = "general"
    session_id: str | None = None


def _owner_email(user: dict | None) -> str | None:
    if not user:
        return None
    return user.get("sub") or user.get("email")


@router.get("/list")
async def list_reports(_user: dict | None = Depends(get_current_user_optional)):
    """列出已生成的切片/个体报告 PDF（slice_* / ent_*），并按归属过滤。"""
    import re

    cleanup_legacy_reports()
    reports = []
    reports_dir = slice_report.REPORTS_DIR
    pat = re.compile(r"^((?:slice|ent)_[a-zA-Z0-9_-]+)\.pdf$", re.I)
    # 兼容旧：slice_key_YYYYMMDD_HHMMSS；新：…_HHMMSS_<uuid8>
    title_pat = re.compile(
        r"^(?:slice|ent)_(.+)_(\d{8})_(\d{6})(?:_[a-f0-9]{8})?$",
        re.I,
    )
    if reports_dir.exists():
        for f in sorted(reports_dir.glob("*.pdf"), reverse=True):
            m = pat.match(f.name)
            if not m:
                continue
            stem = m.group(1)
            if not can_access_report(stem, _user, auth_required=auth_service.AUTH_REQUIRED):
                continue
            tm = title_pat.match(stem)
            if tm:
                _d, _t = tm.group(2), tm.group(3)
                kind = "个体" if stem.lower().startswith("ent_") else get_scenario_label(tm.group(1))
                title = f"{kind} · {_d[:4]}-{_d[4:6]}-{_d[6:8]} {_t[:2]}:{_t[2:4]}"
            else:
                title = stem
            mtime = f.stat().st_mtime
            from datetime import datetime

            dt = datetime.fromtimestamp(mtime)
            reports.append(
                {
                    "report_id": stem,
                    "title": title,
                    "date": dt.strftime("%Y-%m-%d"),
                    "size": f.stat().st_size,
                    "download_url": f"/api/v1/report/{stem}/download",
                }
            )
    return {"items": reports, "total": len(reports), "source": "slice+ent"}

@router.post("/generate")
async def generate_report(
    body: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_plan("subscriber")),
):
    if body.enterprise_id:
        raise HTTPException(
            status_code=400,
            detail="匿名切片模式已停用具名企业报告，请使用 POST /api/v1/report/slice 或对话「生成报告」。",
        )

    try:
        report_id, _, ctx = await generate_slice_report(
            db,
            scenario=body.scenario,
            session_id=body.session_id,
            query=body.query,
            owner=_owner_email(_user),
        )
    except PremiumReportLocked:
        raise _premium_locked()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"切片报告生成失败: {exc}") from exc
    return {
        "report_id": report_id,
        "status": "completed",
        "title": ctx.get("title"),
        "scenario": ctx.get("scenario"),
        "validation": ctx.get("validation"),
        "download_url": f"/api/v1/report/{report_id}/download",
    }


@router.post("/slice")
async def generate_slice(
    body: GenerateSliceReportRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_plan("subscriber")),
):
    try:
        report_id, _, ctx = await generate_slice_report(
            db,
            scenario=body.scenario,
            session_id=body.session_id,
            query=body.query or "生成行业趋势风控报告",
            owner=_owner_email(_user),
        )
    except PremiumReportLocked:
        raise _premium_locked()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"切片报告生成失败: {exc}") from exc
    return {
        "report_id": report_id,
        "status": "completed",
        "title": ctx.get("title"),
        "scenario": ctx.get("scenario"),
        "validation": ctx.get("validation"),
        "download_url": f"/api/v1/report/{report_id}/download",
    }


@router.post("/email")
async def email_report(
    body: EmailReportRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_plan("subscriber")),
):
    if not email_service.is_configured():
        return {"success": False, "message": email_service.NOT_CONFIGURED_MSG}

    if body.enterprise_id:
        return {
            "success": False,
            "message": "匿名模式不支持按企业发邮，请先生成切片报告后手动发送。",
        }

    try:
        report_id, pdf_path, ctx = await generate_slice_report(
            db,
            scenario=body.scenario,
            session_id=body.session_id,
            query="邮件发送风控报告",
            owner=_owner_email(_user),
        )
        title = str(ctx.get("title") or "风控报告")
        from app.services.sync_runner import run_blocking

        await run_blocking(
            email_service.send_slice_report,
            body.recipient,
            title,
            pdf_path,
        )
        return {
            "success": True,
            "message": f"报告已发送至 {body.recipient}",
            "report_id": report_id,
        }
    except HTTPException:
        raise
    except PremiumReportLocked:
        raise _premium_locked()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"邮件发送失败: {exc}") from exc


@router.post("/enterprise")
async def generate_enterprise(
    body: GenerateEnterpriseReportRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_plan("subscriber")),
):
    """个体深度报告：单一样本画像 + 同业基准 + 归因 + 预警（脱敏，仅哈希 id）。"""
    try:
        from app.services.slice_report import generate_enterprise_report

        report_id, _, ctx = await generate_enterprise_report(
            db, body.enterprise_id, owner=_owner_email(_user)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"个体深度报告生成失败: {exc}") from exc
    return {
        "report_id": report_id,
        "status": "completed",
        "title": ctx.get("title"),
        "scenario": ctx.get("scenario"),
        "validation": ctx.get("validation"),
        "download_url": f"/api/v1/report/{report_id}/download",
    }


@router.post("/preview")
async def preview_slice_report(
    body: GenerateSliceReportRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    """HTML 预览（WeasyPrint 同源模板，不生成 PDF 文件）。"""
    try:
        html = await preview_slice_report_html(
            db,
            scenario=body.scenario,
            session_id=body.session_id,
            query=body.query or "生成行业趋势风控报告",
        )
    except PremiumReportLocked:
        raise _premium_locked()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"报告预览失败: {exc}") from exc
    return HTMLResponse(html)


@router.get("/{report_id}/download")
async def download_report(report_id: str, _user: dict | None = Depends(require_plan("subscriber"))):
    path = get_report_path(report_id)
    if not path:
        raise HTTPException(status_code=404, detail="报告不存在")
    if not can_access_report(report_id, _user, auth_required=auth_service.AUTH_REQUIRED):
        raise HTTPException(status_code=403, detail="无权下载该报告")
    filename = f"评估报告_{report_id}.pdf"
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
    )
