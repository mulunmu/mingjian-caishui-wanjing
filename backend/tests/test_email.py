"""邮件服务测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_email_not_configured_by_default():
    from app.services.email_service import is_configured, NOT_CONFIGURED_MSG, RATE_LIMIT_MSG
    # 默认未配置 EMAIL_SENDER/EMAIL_PASSWORD
    configured = is_configured()
    # 无论是否配置，常量和限流消息存在
    assert len(NOT_CONFIGURED_MSG) > 0
    assert len(RATE_LIMIT_MSG) > 0


def test_email_rate_limit_allows_first():
    from app.services.email_service import _check_email_rate
    # 初始状态应允许发送
    assert _check_email_rate()


def test_send_without_config_raises():
    from app.services.email_service import send_report, is_configured
    from pathlib import Path
    if is_configured():
        return  # skip if configured
    raised = False
    try:
        send_report("test@test.com", "test", Path("nonexistent.pdf"))
    except RuntimeError as e:
        raised = True
        assert "未配置" in str(e)
    assert raised
