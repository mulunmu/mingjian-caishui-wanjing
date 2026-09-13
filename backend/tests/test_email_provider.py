"""邮件 Provider 抽象 — 纯单元测试（不真连 SMTP，不发真邮件）。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.email_provider import SendResult, SMTPProvider, HttpApiProvider, get_provider


def test_send_result_defaults():
    r = SendResult(ok=True)
    assert r.ok is True
    assert r.message_id is None
    assert r.error is None
    assert r.provider == "smtp"


def test_smtp_provider_missing_attachment_fails(tmp_path):
    p = SMTPProvider(sender="s@x.com", password="p", host="localhost", port=1025)
    missing = tmp_path / "nope.pdf"
    res = p.send(to="r@x.com", subject="s", body_text="t", attachments=[missing])
    assert res.ok is False
    assert "附件不存在" in res.error


def test_smtp_provider_sends_via_ssl(monkeypatch):
    import smtplib

    calls = {}

    class FakeServer:
        def login(self, sender, password):
            calls["login"] = (sender, password)

        def send_message(self, msg):
            calls["send_message"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: FakeServer())
    p = SMTPProvider(sender="s@x.com", password="p", host="localhost", port=465)
    res = p.send(to="r@x.com", subject="s", body_text="t")
    assert res.ok is True
    assert calls.get("login") == ("s@x.com", "p")


def test_smtp_provider_starttls_port_587(monkeypatch):
    import smtplib

    class FakeServer:
        def __init__(self):
            self.started = False

        def ehlo(self):
            pass

        def has_extn(self, name):
            return name == "starttls"

        def starttls(self, context=None):
            self.started = True

        def login(self, sender, password):
            pass

        def send_message(self, msg):
            pass

        def quit(self):
            pass

    holder = {}

    def fake_smtp(*a, **k):
        holder["srv"] = FakeServer()
        return holder["srv"]

    monkeypatch.setattr(smtplib, "SMTP", fake_smtp)
    p = SMTPProvider(sender="s@x.com", password="p", host="localhost", port=587)
    res = p.send(to="r@x.com", subject="s", body_text="t")
    assert res.ok is True
    assert holder["srv"].started is True


def test_smtp_provider_swallows_smtp_error(monkeypatch):
    import smtplib

    def boom(*a, **k):
        raise ConnectionError("refused")

    monkeypatch.setattr(smtplib, "SMTP_SSL", boom)
    p = SMTPProvider(sender="s@x.com", password="p", host="localhost", port=465)
    res = p.send(to="r@x.com", subject="s", body_text="t")
    assert res.ok is False
    assert "refused" in res.error


def test_http_api_provider_not_configured():
    p = HttpApiProvider(api_key="")
    res = p.send(to="r@x.com", subject="s", body_text="t")
    assert res.ok is False
    assert "未配置" in res.error
    assert p.name == "httpapi"


def test_get_provider_prefers_http_when_api_key(monkeypatch):
    monkeypatch.setenv("EMAIL_API_KEY", "k")
    monkeypatch.delenv("EMAIL_SENDER", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
    assert get_provider().name == "httpapi"


def test_get_provider_smtp_default(monkeypatch):
    monkeypatch.delenv("EMAIL_API_KEY", raising=False)
    assert get_provider().name == "smtp"
