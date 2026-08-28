"""评估报告邮件发送（可选功能，未配置 EMAIL_* 环境变量时不影响其他功能）"""
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

NOT_CONFIGURED_MSG = "邮件服务未配置，请下载后手动发送"
RATE_LIMIT_MSG = "邮件发送过于频繁，请稍后重试"

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
