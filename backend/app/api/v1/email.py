"""邮件交付 API — 报告发送 / 批量发送 / 发送记录 / 重发（企划书 §5.1）。"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.api.deps import require_plan
from app.responses import UTF8JSONResponse
from app.services import (
    auth_service,
    email_log_service,
    email_service,
    trusted_email_service,
    verification_service,
)
from app.services.slice_report import can_access_report, get_report_path, read_report_snapshot
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/emails", tags=["emails"])


def _owner_email(user: dict | None) -> str | None:
    if not user:
        return None
    return user.get("sub") or user.get("email")


def _report_title(report_id: str) -> str:
    snap = read_report_snapshot(report_id)
    return (snap or {}).get("title") or "风控报告"


def _send_error_status(detail: str) -> int:
    return 429 if "过于频繁" in detail else 503


class SendEmailRequest(BaseModel):
    report_id: str
    recipient: EmailStr
    code: str | None = None
    remember: bool = False


class BatchEmailRequest(BaseModel):
    report_ids: list[str]
    recipient: EmailStr
    code: str | None = None
    remember: bool = False


@router.post("/send", response_class=UTF8JSONResponse)
async def send_email(
    body: SendEmailRequest,
    _user: dict | None = Depends(require_plan("subscriber")),
):
    """发送单份报告到指定收件人。受信直达；非受信需验证码（企划书阶段 C）。"""
    if not email_service.is_configured():
        raise HTTPException(status_code=503, detail=email_service.NOT_CONFIGURED_MSG)

    owner = _owner_email(_user) or ""
    recipient = body.recipient.strip().lower()
    if get_report_path(body.report_id) is None or not can_access_report(
        body.report_id, _user, auth_required=auth_service.AUTH_REQUIRED
    ):
        raise HTTPException(status_code=404, detail="报告不存在或无权访问")

    if not trusted_email_service.is_trusted(owner, recipient):
        if not body.code:
            raise HTTPException(status_code=428, detail="请先验证收件邮箱后发送")
        try:
            await run_blocking(
                verification_service.consume_code, recipient, "send_email", body.code
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if body.remember:
            await run_blocking(
                trusted_email_service.add_trusted_email, owner, recipient, "verified"
            )

    title = _report_title(body.report_id)
    try:
        result = await email_service.send_report_to(
            recipient,
            title,
            get_report_path(body.report_id),
            report_id=body.report_id,
            identity=owner,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=_send_error_status(str(exc)), detail=str(exc)) from exc
    return {"success": True, "message": f"报告已发送至 {recipient}", "log_id": result["log_id"]}


@router.post("/batch", response_class=UTF8JSONResponse)
async def batch_email(
    body: BatchEmailRequest,
    _user: dict | None = Depends(require_plan("subscriber")),
):
    """批量发送多份报告到同一收件人；逐份失败不阻断整体，返回汇总。"""
    if not email_service.is_configured():
        raise HTTPException(status_code=503, detail=email_service.NOT_CONFIGURED_MSG)

    owner = _owner_email(_user) or ""
    recipient = body.recipient.strip().lower()

    if not trusted_email_service.is_trusted(owner, recipient):
        if not body.code:
            raise HTTPException(status_code=428, detail="请先验证收件邮箱后发送")
        try:
            await run_blocking(
                verification_service.consume_code, recipient, "send_email", body.code
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if body.remember:
            await run_blocking(
                trusted_email_service.add_trusted_email, owner, recipient, "verified"
            )

    results: list[dict] = []
    sent = failed = 0
    for report_id in body.report_ids:
        if get_report_path(report_id) is None or not can_access_report(
            report_id, _user, auth_required=auth_service.AUTH_REQUIRED
        ):
            results.append({"report_id": report_id, "ok": False, "message": "报告不存在或无权访问"})
            failed += 1
            continue
        try:
            await email_service.send_report_to(
                recipient,
                _report_title(report_id),
                get_report_path(report_id),
                report_id=report_id,
                identity=owner,
            )
            results.append({"report_id": report_id, "ok": True, "message": "已发送"})
            sent += 1
        except RuntimeError as exc:
            results.append({"report_id": report_id, "ok": False, "message": str(exc)})
            failed += 1
    return {"success": failed == 0, "sent": sent, "failed": failed, "results": results}


@router.get("/logs", response_class=UTF8JSONResponse)
async def list_email_logs(
    recipient: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _user: dict | None = Depends(require_plan("subscriber")),
):
    """发送记录（全程审计）。普通用户只看自己的；admin 可看全部。"""
    owner = _owner_email(_user) or ""
    is_admin = ((_user or {}).get("role") or "user") == "admin"
    return await run_blocking(
        email_log_service.list_logs,
        owner=None if is_admin else owner,
        recipient=recipient,
        kind=kind,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/trusted", response_class=UTF8JSONResponse)
async def list_trusted_emails(_user: dict | None = Depends(require_plan("subscriber"))):
    """当前用户的受信邮箱列表（注册即受信 + 验证后受信）。"""
    owner = _owner_email(_user) or ""
    items = await run_blocking(trusted_email_service.list_trusted_emails, owner)
    return {"items": items, "total": len(items)}


@router.delete("/trusted/{email}", response_class=UTF8JSONResponse)
async def remove_trusted_email(
    email: str,
    _user: dict | None = Depends(require_plan("subscriber")),
):
    """移除一个受信邮箱（下次发送到该邮箱需重新验证）。"""
    owner = _owner_email(_user) or ""
    ok = await run_blocking(trusted_email_service.remove_trusted_email, owner, email)
    if not ok:
        raise HTTPException(status_code=404, detail="受信邮箱不存在")
    return {"success": True, "message": "已移除"}


@router.post("/{log_id}/resend", response_class=UTF8JSONResponse)
async def resend_email(
    log_id: int,
    _user: dict | None = Depends(require_plan("subscriber")),
):
    """重发一封报告邮件（仅报告类；验证码类不支持；报告已删则拒绝）。"""
    owner = _owner_email(_user) or ""
    log = await run_blocking(email_log_service.get_log, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="发送记录不存在")

    is_admin = ((_user or {}).get("role") or "user") == "admin"
    if not is_admin and (log.get("owner") or "") != owner:
        raise HTTPException(status_code=403, detail="无权操作该发送记录")
    if log.get("kind") == "verify_code":
        raise HTTPException(status_code=400, detail="验证码邮件不支持重发")

    report_id = log.get("report_id")
    if not report_id or get_report_path(report_id) is None:
        raise HTTPException(status_code=404, detail="报告已被删除，无法重发")

    recipient = log["recipient"]
    try:
        result = await email_service.send_report_to(
            recipient,
            _report_title(report_id),
            get_report_path(report_id),
            report_id=report_id,
            identity=owner,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=_send_error_status(str(exc)), detail=str(exc)) from exc
    return {"success": True, "message": f"已重发至 {recipient}", "log_id": result["log_id"]}
