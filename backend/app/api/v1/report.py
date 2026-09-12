import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional, require_plan
from app.db.session import get_db
from app.services import auth_service, email_service, slice_report
from app.services.report_templates import PremiumReportLocked, get_scenario_label, zh_report_title
from app.services.slice_report import (
    build_report_detail,
    can_access_report,
    cleanup_legacy_reports,
    generate_slice_report,
    get_report_path,
    preview_enterprise_report_html,
    preview_slice_report_html,
    read_report_snapshot,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/report", tags=["report"])


def _safe_filename(name: str) -> str:
    """清洗报告标题为合法文件名：去 Windows/Unix 非法字符、控制符与首尾空白。"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", name or "").strip()
    return cleaned or "评估报告"


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
    industry_l1: str | None = None
    province: str | None = None


class GenerateSliceReportRequest(BaseModel):
    scenario: str | None = None
    session_id: str | None = None
    query: str | None = None
    industry_l1: str | None = None
    province: str | None = None


class GenerateEnterpriseReportRequest(BaseModel):
    enterprise_id: str


class ValidateWizardRequest(BaseModel):
    scenario: str | None = None
    industry_l1: str | None = None
    province: str | None = None
    enterprise_id: str | None = None


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
                # 定制报告：用快照里的真实标题（AI 判定的章节组合），而非泛化场景标签
                if tm.group(1) == "custom":
                    snap = slice_report.read_report_snapshot(stem) or {}
                    title = snap.get("title") or title
            else:
                title = stem
            mtime = f.stat().st_mtime
            from datetime import datetime

            dt = datetime.fromtimestamp(mtime)
            item = {
                "report_id": stem,
                "title": title,
                "date": dt.strftime("%Y-%m-%d"),
                "size": f.stat().st_size,
                "download_url": f"/api/v1/report/{stem}/download",
            }
            if stem.lower().startswith("ent_"):
                meta = slice_report.read_report_meta(stem) or {}
                item["enterprise_id"] = meta.get("enterprise_id")
            reports.append(item)
    return {"items": reports, "total": len(reports), "source": "slice+ent"}

@router.post("/generate")
async def generate_report(
    body: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_plan("subscriber")),
):
    if body.enterprise_id:
        # 统一入口：带 enterprise_id 走单企业风险披露报告（脱敏、无 LLM），不再报 400。
        try:
            from app.services.slice_report import generate_enterprise_report

            report_id, _, ctx = await generate_enterprise_report(
                db, body.enterprise_id, owner=_owner_email(_user)
            )
        except ValueError as exc:
            msg = str(exc)
            if "未找到" in msg or "不存在" in msg:
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc
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

    try:
        report_id, _, ctx = await generate_slice_report(
            db,
            scenario=body.scenario,
            session_id=body.session_id,
            query=body.query,
            owner=_owner_email(_user),
            industry_l1=body.industry_l1,
            province=body.province,
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
            industry_l1=body.industry_l1,
            province=body.province,
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


@router.post("/validate-wizard")
async def validate_wizard(
    body: ValidateWizardRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_plan("subscriber")),
):
    """固定场景向导预校验：无样本 / 无可用章时 ok=false + reason，前端拦截生成。"""
    from app.services.slice_report import validate_wizard_report

    try:
        return await validate_wizard_report(
            db,
            scenario=body.scenario,
            industry_l1=body.industry_l1,
            province=body.province,
            enterprise_id=body.enterprise_id,
        )
    except Exception as exc:
        logger.warning("validate-wizard failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"预校验失败: {exc}") from exc


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

    login_email = (_owner_email(_user) or "").strip().lower()
    recipient = str(body.recipient).strip().lower()
    if not login_email or recipient != login_email:
        raise HTTPException(
            status_code=403,
            detail="邮件仅可发送至当前登录账号邮箱。",
        )

    try:
        report_id, pdf_path, ctx = await generate_slice_report(
            db,
            scenario=body.scenario,
            session_id=body.session_id,
            query="邮件发送风控报告",
            owner=login_email,
        )
        title = str(ctx.get("title") or "风控报告")
        from app.services.sync_runner import run_blocking

        await run_blocking(
            email_service.send_slice_report,
            recipient,
            title,
            pdf_path,
        )
        return {
            "success": True,
            "message": f"报告已发送至 {recipient}",
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
        msg = str(exc)
        # 预/后置校验失败 → 422；真正找不到样本 → 404
        if "未找到" in msg or "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
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


@router.post("/enterprise/preview")
async def preview_enterprise_report(
    body: GenerateEnterpriseReportRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(require_plan("subscriber")),
):
    """个体财务分析报告 HTML 预览（与下载 PDF 同源模板）。需订阅鉴权。"""
    try:
        html = await preview_enterprise_report_html(db, enterprise_id=body.enterprise_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"个体报告预览失败: {exc}") from exc
    return HTMLResponse(html)


@router.post("/preview")
async def preview_slice_report(
    body: GenerateSliceReportRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_plan("subscriber")),
):
    """HTML 预览（WeasyPrint 同源模板，不生成 PDF 文件）。需订阅鉴权。"""
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


@router.get("/{report_id}")
async def get_report_detail(report_id: str, _user: dict | None = Depends(require_plan("subscriber"))):
    """报告结构化详情（与下载 PDF 同源快照回读）。无快照/无权限 → 404/403。"""
    if not can_access_report(report_id, _user, auth_required=auth_service.AUTH_REQUIRED):
        raise HTTPException(status_code=403, detail="无权访问该报告")
    snap = read_report_snapshot(report_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="报告不存在或未生成快照")
    return build_report_detail(report_id, snap)


@router.get("/{report_id}/download")
async def download_report(report_id: str, _user: dict | None = Depends(require_plan("subscriber"))):
    path = get_report_path(report_id)
    if not path:
        raise HTTPException(status_code=404, detail="报告不存在")
    if not can_access_report(report_id, _user, auth_required=auth_service.AUTH_REQUIRED):
        raise HTTPException(status_code=403, detail="无权下载该报告")
    snap = read_report_snapshot(report_id)
    title = (snap or {}).get("title") or zh_report_title(report_id) or "评估报告"
    filename = f"{_safe_filename(title)}.pdf"
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
    )
