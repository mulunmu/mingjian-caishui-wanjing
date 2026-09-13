"""评估报告邮件发送（可选功能，未配置 EMAIL_* 环境变量时不影响其他功能）。

- 发送内核统一走 `EmailProvider`（SMTPProvider 主路径，替换 yagmail）+ 统一模板 + EmailLog 审计。
- 指数退避重试由 `send_report_to`（async）承担；阻塞 smtplib 经 `run_blocking` 跑线程池。
- 双层配额（§7.2(4)）：全局每小时 + 按身份每小时；验证码发送不在此配额内
  （由 verification_service 按邮箱/IP 单独控制）。
"""
import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from app.services import email_log_service, email_templates
from app.services.email_provider import SendResult, get_provider
from app.services.sync_runner import run_blocking

load_dotenv()

NOT_CONFIGURED_MSG = "邮件服务未配置，请下载后手动发送"
RATE_LIMIT_MSG = "邮件发送过于频繁，请稍后重试"
# 验证码场景专用文案（NOT_CONFIGURED_MSG 的「请下载后手动发送」只适用于报告）
NOT_CONFIGURED_CODE_MSG = "邮件服务未配置，暂时无法发送验证码，请联系管理员"

# 发信失败指数退避重试次数（§2.2）
EMAIL_RETRY_MAX = int(os.getenv("EMAIL_RETRY_MAX", "3"))

# ── 双层配额（§7.2(4)）──
_EMAIL_TIMESTAMPS: list[float] = []
_EMAIL_HOURLY_LIMIT = int(os.getenv("EMAIL_HOURLY_LIMIT", "200"))
_IDENTITY_TIMESTAMPS: dict[str, list[float]] = {}
_IDENTITY_HOURLY_LIMIT = int(os.getenv("EMAIL_IDENTITY_HOURLY_LIMIT", "20"))


def is_configured() -> bool:
    return bool(os.getenv("EMAIL_SENDER") and os.getenv("EMAIL_PASSWORD"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_email_rate() -> bool:
    """遗留：全局每小时配额（保留给 send_slice_report 与既有单测）。"""
    now = time.time()
    cutoff = now - 3600
    while _EMAIL_TIMESTAMPS and _EMAIL_TIMESTAMPS[0] < cutoff:
        _EMAIL_TIMESTAMPS.pop(0)
    return len(_EMAIL_TIMESTAMPS) < _EMAIL_HOURLY_LIMIT


def _check_rate(identity: str | None) -> bool:
    """双层配额：全局 + 按身份（§7.2(4)）。"""
    if not _check_email_rate():
        return False
    if identity:
        now = time.time()
        cutoff = now - 3600
        bucket = _IDENTITY_TIMESTAMPS.setdefault(identity, [])
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= _IDENTITY_HOURLY_LIMIT:
            return False
    return True


def _record_send(identity: str | None) -> None:
    now = time.time()
    _EMAIL_TIMESTAMPS.append(now)
    if identity:
        _IDENTITY_TIMESTAMPS.setdefault(identity, []).append(now)


def _finish_log(log_id: int, result: SendResult, retry_count: int = 0) -> None:
    email_log_service.update_log(
        log_id,
        status="sent" if result.ok else "failed",
        message_id=result.message_id,
        error=result.error,
        retry_count=retry_count,
        sent_at=_now() if result.ok else None,
    )


def send_slice_report(recipient: str, report_title: str, pdf_path: Path) -> dict:
    """发送匿名切片报告（主题不含企业名）。保留旧签名：同步、单次、全局配额。"""
    if not is_configured():
        raise RuntimeError(NOT_CONFIGURED_MSG)
    if not _check_email_rate():
        raise RuntimeError(RATE_LIMIT_MSG)
    _EMAIL_TIMESTAMPS.append(time.time())

    subject, body_text, body_html = email_templates.report_email(report_title)
    provider = get_provider()
    sender = os.getenv("EMAIL_SENDER", "")
    log_id = email_log_service.record_log(
        sender=sender,
        recipient=recipient,
        subject=subject,
        kind="report",
        provider=provider.name,
        status="pending",
    )
    result = provider.send(
        to=recipient,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        attachments=[pdf_path],
    )
    _finish_log(log_id, result)
    if not result.ok:
        raise RuntimeError(result.error or "邮件发送失败")
    return {"log_id": log_id}


def send_report(recipient: str, enterprise_name: str, pdf_path: Path) -> None:
    """遗留：enterprise_name 应为 display_label，不含具名企业。"""
    send_slice_report(recipient, enterprise_name or "风控报告", pdf_path)


async def send_report_to(
    recipient: str,
    title: str,
    pdf_path: Path,
    *,
    report_id: str | None = None,
    identity: str | None = None,
) -> dict:
    """发送报告（Provider + 模板 + EmailLog + 指数退避重试 + 双层配额）。

    identity 为发送者身份（登录邮箱），用于按身份配额；失败抛 RuntimeError（中文）。
    """
    if not is_configured():
        raise RuntimeError(NOT_CONFIGURED_MSG)
    if not _check_rate(identity):
        raise RuntimeError(RATE_LIMIT_MSG)
    _record_send(identity)

    subject, body_text, body_html = email_templates.report_email(title)
    provider = get_provider()
    sender = os.getenv("EMAIL_SENDER", "")
    log_id = email_log_service.record_log(
        owner=identity,
        sender=sender,
        recipient=recipient,
        subject=subject,
        report_id=report_id,
        kind="report",
        provider=provider.name,
        status="pending",
    )

    attempts = max(1, EMAIL_RETRY_MAX)
    result = SendResult(ok=False, error="未尝试", provider=provider.name)
    retry_count = 0
    for attempt in range(attempts):
        result = await run_blocking(
            provider.send,
            to=recipient,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            attachments=[pdf_path],
        )
        if result.ok:
            retry_count = attempt
            break
        if attempt < attempts - 1:
            await asyncio.sleep(2 ** attempt)
    else:
        retry_count = attempts

    _finish_log(log_id, result, retry_count=retry_count)
    if not result.ok:
        raise RuntimeError(result.error or "邮件发送失败")
    return {"log_id": log_id, "message_id": result.message_id}


def send_verification_code(recipient: str, code: str, ttl_minutes: int = 5) -> dict:
    """发送验证码邮件。

    独立于报告配额（不复用 _check_rate）：配额由 verification_service 按邮箱/IP 控制。
    注意：code 不进日志。统一落 EmailLog（kind=verify_code）。
    """
    if not is_configured():
        raise RuntimeError(NOT_CONFIGURED_CODE_MSG)

    subject, body_text, body_html = email_templates.verification_code_email(code, ttl_minutes)
    provider = get_provider()
    sender = os.getenv("EMAIL_SENDER", "")
    log_id = email_log_service.record_log(
        owner=recipient,
        sender=sender,
        recipient=recipient,
        subject=subject,
        kind="verify_code",
        provider=provider.name,
        status="pending",
    )
    result = provider.send(
        to=recipient,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
    _finish_log(log_id, result)
    if not result.ok:
        raise RuntimeError(result.error or "验证码邮件发送失败")
    return {"log_id": log_id}
