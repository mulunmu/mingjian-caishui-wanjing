"""认证服务单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.auth_service import (
    hash_password, verify_password, register_user,
    authenticate_user, create_access_token, verify_token,
)


def test_hash_and_verify():
    pw = "test-password-123"
    h = hash_password(pw)
    assert verify_password(pw, h)
    assert not verify_password("wrong", h)


def test_register_and_auth():
    email = "test-user@example.com"
    pw = "secure123"
    try:
        register_user(email, pw)
    except ValueError:
        pass  # may already exist from previous test run
    user = authenticate_user(email, pw)
    assert user is not None
    assert user["email"] == email


def test_register_duplicate():
    email = "dup@test.com"
    pw = "pass123456"
    try:
        register_user(email, pw)
    except ValueError:
        pass
    raised = False
    try:
        register_user(email, "other456")
    except ValueError:
        raised = True
    assert raised


def test_authenticate_wrong_password():
    try:
        register_user("auth-test@example.com", "correct123")
    except ValueError:
        pass
    assert authenticate_user("auth-test@example.com", "wrong") is None


def test_create_and_verify_token():
    token = create_access_token("user@test.com", "user")
    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "user@test.com"
    assert payload["role"] == "user"


def test_verify_invalid_token():
    assert verify_token("invalid-token-here") is None
    assert verify_token("") is None
    assert verify_token("Bearer garbage") is None


def test_token_with_bearer_prefix():
    token = create_access_token("b@t.com", "admin")
    payload = verify_token(f"Bearer {token}")
    assert payload is not None
    assert payload["sub"] == "b@t.com"
