"""评估报告邮件发送（可选功能，未配置 EMAIL_* 环境变量时不影响其他功能）"""
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

NOT_CONFIGURED_MSG = "邮件服务未配置，请下载后手动发送"
RATE_LIMIT_MSG = "邮件发送过于频繁，请稍后重试"
# 验证码场景专用文案（NOT_CONFIGURED_MSG 的「请下载后手动发送」只适用于报告）
NOT_CONFIGURED_CODE_MSG = "邮件服务未配置，暂时无法发送验证码，请联系管理员"

# 每小时最多 10 封，防滥发
_EMAIL_TIMESTAMPS: list[float] = []
_EMAIL_HOURLY_LIMIT = 10


def is_configured() -> bool:
    return bool(os.getenv("EMAIL_SENDER") and os.getenv("EMAIL_PASSWORD"))


def _check_email_rate() -> bool:
    now = time.time()
    cutoff = now - 3600
    while _EMAIL_TIMESTAMPS and _EMAIL_TIMESTAMPS[0] < cutoff:
        _EMAIL_TIMESTAMPS.pop(0)
    return len(_EMAIL_TIMESTAMPS) < _EMAIL_HOURLY_LIMIT


def send_slice_report(recipient: str, report_title: str, pdf_path: Path) -> None:
    """发送匿名切片报告（主题不含企业名）。"""
    if not is_configured():
        raise RuntimeError(NOT_CONFIGURED_MSG)
    if not _check_email_rate():
        raise RuntimeError(RATE_LIMIT_MSG)
    _EMAIL_TIMESTAMPS.append(time.time())

    import yagmail

    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")

    yag = yagmail.SMTP(user=sender, password=password, host=host)
    try:
        yag.send(
            to=recipient,
            subject=f"【风控报告】{report_title}",
            contents=[
                f"您好，\n\n附件为「{report_title}」（匿名行业/地区切片），请查收。\n\n"
                "本报告由明鉴・财税票・万景自动生成，仅供参考，不构成投资建议或法律意见。",
            ],
            attachments=str(pdf_path),
        )
    finally:
        yag.close()


def send_report(recipient: str, enterprise_name: str, pdf_path: Path) -> None:
    """遗留：enterprise_name 应为 display_label，不含具名企业。"""
    send_slice_report(recipient, enterprise_name or "风控报告", pdf_path)


# 国内 SMTP 默认值（未配置 EMAIL_SMTP_HOST 时使用；不改动 send_slice_report 的既有默认）
DEFAULT_SMTP_HOST_CN = "smtp.qq.com"
DEFAULT_SMTP_PORT_CN = 465


def _smtp_host_port() -> tuple[str, int]:
    host = os.getenv("EMAIL_SMTP_HOST", DEFAULT_SMTP_HOST_CN)
    try:
        port = int(os.getenv("EMAIL_SMTP_PORT", str(DEFAULT_SMTP_PORT_CN)))
    except ValueError:
        port = DEFAULT_SMTP_PORT_CN
    return host, port


def send_verification_code(recipient: str, code: str, ttl_minutes: int = 5) -> None:
    """发送验证码邮件。

    独立于 send_slice_report：不复用 _check_email_rate（那是全局限 10 封/小时，
    会把验证码发送一起卡死）。配额由 verification_service 按邮箱/IP 单独控制。
    注意：code 不进日志。
    """
    if not is_configured():
        raise RuntimeError(NOT_CONFIGURED_CODE_MSG)

    import yagmail

    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    host, port = _smtp_host_port()

    yag = yagmail.SMTP(user=sender, password=password, host=host, port=port)
    try:
        yag.send(
            to=recipient,
            subject="【明鉴】邮箱注册验证码",
            contents=[
                f"您好，\n\n您的注册验证码是：{code}\n\n"
                f"验证码 {ttl_minutes} 分钟内有效，请勿转发给他人。\n"
                "如非本人操作，请忽略本邮件。\n\n"
                "明鉴・财税票・万景",
            ],
        )
    finally:
        yag.close()
