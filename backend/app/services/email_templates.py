"""邮件模板 — 统一 Header / Footer / 固定免责声明（企划书 §7.2）。

验证码邮件与报告邮件共用同一签名与免责声明，保证品牌与合规一致。
"""
from __future__ import annotations

# 固定免责声明（§7.2(2)，逐字对齐，勿改）
DISCLAIMER = "本报告由明鉴·财税票·万景自动生成，仅供参考，不构成审计意见、投资建议或信贷审批依据"

_BRAND = "明鉴·财税票·万景"

_FOOTER_TEXT = f"{_BRAND}\n{DISCLAIMER}"
_FOOTER_HTML = (
    f"<hr><p style='color:#888;font-size:12px'>{_BRAND}<br>{DISCLAIMER}</p>"
)


def verification_code_email(code: str, ttl_minutes: int) -> tuple[str, str, str]:
    """返回 (subject, text, html)。"""
    subject = "【明鉴】邮箱验证码"
    text = (
        f"您好，\n\n"
        f"您的验证码是：{code}\n\n"
        f"验证码 {ttl_minutes} 分钟内有效，请勿转发给他人。\n"
        f"如非本人操作，请忽略本邮件。\n\n"
        f"{_FOOTER_TEXT}"
    )
    html = (
        f"<p>您好，</p>"
        f"<p>您的验证码是：<strong style='font-size:20px'>{code}</strong></p>"
        f"<p>验证码 {ttl_minutes} 分钟内有效，请勿转发给他人。</p>"
        f"<p>如非本人操作，请忽略本邮件。</p>"
        f"{_FOOTER_HTML}"
    )
    return subject, text, html


def report_email(report_title: str) -> tuple[str, str, str]:
    """返回 (subject, text, html)。脱敏报告，正文不含可定位企业标识。"""
    subject = f"【风控报告】{report_title}"
    text = (
        f"您好，\n\n"
        f"附件为「{report_title}」（匿名行业/地区切片），请查收。\n\n"
        f"{_FOOTER_TEXT}"
    )
    html = (
        f"<p>您好，</p>"
        f"<p>附件为「{report_title}」（匿名行业/地区切片），请查收。</p>"
        f"{_FOOTER_HTML}"
    )
    return subject, text, html
