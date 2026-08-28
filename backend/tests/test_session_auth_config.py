"""session 连接池 + 生产认证配置校验"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import _pool_kwargs
from app.services.auth_service import validate_production_config, _DEV_JWT_SECRET


def test_pool_kwargs_uses_queue_pool_by_default():
    kw = _pool_kwargs()
    assert "pool_size" in kw
    assert kw["pool_pre_ping"] is True
    assert kw["pool_size"] >= 1


def test_pool_kwargs_nullpool_when_disabled(monkeypatch):
    monkeypatch.setenv("DB_POOL_DISABLED", "true")
    kw = _pool_kwargs()
    from sqlalchemy.pool import NullPool

    assert kw.get("poolclass") is NullPool


def test_validate_production_config_demo_mode(monkeypatch):
    monkeypatch.delenv("AUTH_REQUIRED", raising=False)
    out = validate_production_config()
    assert out["ok"] is True
    assert out["auth_required"] is False


def test_validate_production_config_rejects_weak_secret(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("JWT_SECRET", _DEV_JWT_SECRET)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    out = validate_production_config()
    assert out["ok"] is False
    assert any("JWT_SECRET" in e for e in out["errors"])


def test_validate_production_config_rejects_wildcard_cors(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    out = validate_production_config()
    assert out["ok"] is False
    assert any("CORS" in e for e in out["errors"])
