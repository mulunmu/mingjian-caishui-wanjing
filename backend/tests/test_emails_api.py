"""邮件交付 API — 纯 mock 集成测试（不真发邮件，不碰真库）。

覆盖 /api/v1/emails 下的 send / batch / logs / trusted / resend。
鉴权用真实签发的 subscriber JWT，业务依赖全部 patch。
"""
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import create_access_token


def _headers(email: str = "owner@example.com") -> dict:
    token = create_access_token(email, "user", "subscriber")
    return {"Authorization": f"Bearer {token}"}


def _client() -> TestClient:
    return TestClient(app)


def test_send_email_not_configured_returns_503():
    with patch("app.services.email_service.is_configured", return_value=False):
        resp = _client().post(
            "/api/v1/emails/send",
            json={"report_id": "slice_x", "recipient": "r@x.com"},
            headers=_headers(),
        )
    assert resp.status_code == 503
    assert "未配置" in resp.json()["detail"]


def test_send_email_untrusted_without_code_returns_428():
    with patch("app.services.email_service.is_configured", return_value=True), patch(
        "app.api.v1.email.get_report_path", return_value=Path("/tmp/x.pdf")
    ), patch("app.api.v1.email.can_access_report", return_value=True), patch(
        "app.services.trusted_email_service.is_trusted", return_value=False
    ):
        resp = _client().post(
            "/api/v1/emails/send",
            json={"report_id": "slice_x", "recipient": "r@x.com"},
            headers=_headers(),
        )
    assert resp.status_code == 428
    assert "验证" in resp.json()["detail"]


def test_send_email_trusted_sends():
    send = AsyncMock(return_value={"log_id": 1, "message_id": "m1"})
    with patch("app.services.email_service.is_configured", return_value=True), patch(
        "app.services.email_service.send_report_to", new=send
    ), patch("app.api.v1.email.get_report_path", return_value=Path("/tmp/x.pdf")), patch(
        "app.api.v1.email.can_access_report", return_value=True
    ), patch(
        "app.api.v1.email.read_report_snapshot", return_value={"title": "报告A"}
    ), patch(
        "app.services.trusted_email_service.is_trusted", return_value=True
    ):
        resp = _client().post(
            "/api/v1/emails/send",
            json={"report_id": "slice_x", "recipient": "r@x.com"},
            headers=_headers(),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["log_id"] == 1
    send.assert_awaited_once()


def test_batch_email_trusted_sends_all():
    send = AsyncMock(return_value={"log_id": 1, "message_id": "m1"})
    with patch("app.services.email_service.is_configured", return_value=True), patch(
        "app.services.email_service.send_report_to", new=send
    ), patch("app.api.v1.email.get_report_path", return_value=Path("/tmp/x.pdf")), patch(
        "app.api.v1.email.can_access_report", return_value=True
    ), patch(
        "app.api.v1.email.read_report_snapshot", return_value={"title": "报告A"}
    ), patch(
        "app.services.trusted_email_service.is_trusted", return_value=True
    ):
        resp = _client().post(
            "/api/v1/emails/batch",
            json={"report_ids": ["a", "b"], "recipient": "r@x.com"},
            headers=_headers(),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] == 2
    assert body["failed"] == 0
    assert send.await_count == 2


def test_list_trusted_emails():
    items = [{"email": "a@x.com", "source": "register", "verified_at": None}]
    with patch("app.services.trusted_email_service.list_trusted_emails", return_value=items):
        resp = _client().get("/api/v1/emails/trusted", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "a@x.com"


def test_remove_trusted_email_not_found_404():
    with patch("app.services.trusted_email_service.remove_trusted_email", return_value=False):
        resp = _client().delete("/api/v1/emails/trusted/r@x.com", headers=_headers())
    assert resp.status_code == 404


def test_list_logs():
    with patch(
        "app.services.email_log_service.list_logs",
        return_value={"items": [], "total": 0},
    ):
        resp = _client().get("/api/v1/emails/logs", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_resend_not_found_404():
    with patch("app.services.email_log_service.get_log", return_value=None):
        resp = _client().post("/api/v1/emails/123/resend", headers=_headers())
    assert resp.status_code == 404
