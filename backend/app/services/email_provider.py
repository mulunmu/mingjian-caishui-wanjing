"""邮件 Provider 抽象 — 用标准库 smtplib 替换 yagmail 主路径（企划书 §2.2）。

- `EmailProvider` 协议定义统一发送接口。
- `SMTPProvider`：465 走 SSL / 587 走 STARTTLS，附件以字节读取。
- `HttpApiProvider`：占位 —— 无 `EMAIL_API_KEY` 时返回「未配置」。
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol, runtime_checkable

DEFAULT_SMTP_HOST = "smtp.qq.com"
DEFAULT_SMTP_PORT = 465


@dataclass
class SendResult:
    ok: bool
    message_id: str | None = None
    error: str | None = None
    provider: str = "smtp"


@runtime_checkable
class EmailProvider(Protocol):
    name: str

    def send(
        self,
        *,
        to: str,
        subject: str,
        body_text: str,
        body_html: str = "",
        attachments: list[Path] | None = None,
    ) -> SendResult: ...


class SMTPProvider:
    name = "smtp"

    def __init__(
        self,
        *,
        sender: str,
        password: str,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self.sender = sender
        self.password = password
        self.host = host or os.getenv("EMAIL_SMTP_HOST", DEFAULT_SMTP_HOST)
        try:
            self.port = int(port or os.getenv("EMAIL_SMTP_PORT", str(DEFAULT_SMTP_PORT)))
        except ValueError:
            self.port = DEFAULT_SMTP_PORT

    def send(
        self,
        *,
        to: str,
        subject: str,
        body_text: str,
        body_html: str = "",
        attachments: list[Path] | None = None,
    ) -> SendResult:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body_text or "")
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        for path in attachments or []:
            p = Path(path)
            if not p.exists():
                return SendResult(ok=False, error=f"附件不存在: {p.name}", provider=self.name)
            msg.add_attachment(
                p.read_bytes(),
                maintype="application",
                subtype="octet-stream",
                filename=p.name,
            )

        use_ssl = self.port == 465
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(
                    self.host, self.port, timeout=30, context=ssl.create_default_context()
                )
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=30)
                server.ehlo()
                if server.has_extn("starttls"):
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
            server.login(self.sender, self.password)
            server.send_message(msg)
            return SendResult(ok=True, message_id=msg.get("Message-ID"), provider=self.name)
        except Exception as exc:
            return SendResult(ok=False, error=str(exc), provider=self.name)
        finally:
            try:
                server.quit()
            except Exception:
                pass


class HttpApiProvider:
    name = "httpapi"

    def __init__(self, *, api_key: str | None = None, endpoint: str | None = None) -> None:
        self.api_key = api_key or os.getenv("EMAIL_API_KEY", "")
        self.endpoint = endpoint or os.getenv("EMAIL_API_ENDPOINT", "")

    def send(self, **kwargs) -> SendResult:
        return SendResult(
            ok=False,
            error="HTTP 邮件通道未配置（未提供 EMAIL_API_KEY）",
            provider=self.name,
        )


def get_provider() -> EmailProvider:
    """按环境返回可用 Provider：有 EMAIL_API_KEY 走 HttpApi，否则 SMTP。"""
    if os.getenv("EMAIL_API_KEY"):
        return HttpApiProvider()
    return SMTPProvider(
        sender=os.getenv("EMAIL_SENDER", ""),
        password=os.getenv("EMAIL_PASSWORD", ""),
    )
