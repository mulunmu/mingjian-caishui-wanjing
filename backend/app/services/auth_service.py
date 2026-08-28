"""认证服务 — PostgreSQL 用户表 + 内存 L1；JWT"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

logger = logging.getLogger(__name__)

_DEV_JWT_SECRET = "risk-assessment-dev-jwt-do-not-use-in-prod"
JWT_SECRET = os.getenv("JWT_SECRET") or _DEV_JWT_SECRET
if not os.getenv("JWT_SECRET"):
    logger.warning("JWT_SECRET unset; using fixed demo secret (set JWT_SECRET in production)")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

_users_fallback: dict[str, dict] = {}
_tables_ready = False

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
# 鉴权开启时默认关闭自助注册，避免任意人注册即获全站访问
ALLOW_SELF_REGISTER = os.getenv("ALLOW_SELF_REGISTER", "false").lower() == "true"
# 本地演示一键登录（不向前端下发口令）；生产务必 false
DEMO_LOGIN_ENABLED = os.getenv("DEMO_LOGIN_ENABLED", "false").lower() == "true"
_MIN_PASSWORD_LEN = 8 if AUTH_REQUIRED else 6


def validate_production_config() -> dict:
    """AUTH_REQUIRED=true 时校验 JWT / CORS；启动前调用。"""
    auth_required = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
    if not auth_required:
        return {"ok": True, "auth_required": False, "errors": []}

    errors: list[str] = []
    secret = (os.getenv("JWT_SECRET") or "").strip()
    if not secret or secret == _DEV_JWT_SECRET or len(secret) < 32:
        errors.append("AUTH_REQUIRED=true 时必须设置至少 32 字符的 JWT_SECRET（不得使用演示默认值）")
    cors = (os.getenv("CORS_ORIGINS") or "*").strip()
    if cors == "*" or not cors:
        errors.append("AUTH_REQUIRED=true 时 CORS_ORIGINS 不得为 *，需指定前端域名（逗号分隔）")
    return {"ok": not errors, "auth_required": True, "errors": errors}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _ensure_tables() -> bool:
    global _tables_ready
    if _tables_ready:
        return True
    try:
        from app.db.session import Base
        from app.db.urls import get_sync_engine
        import app.models  # noqa: F401

        eng = get_sync_engine()
        Base.metadata.create_all(eng, tables=[app.models.AppUser.__table__])
        _tables_ready = True
        return True
    except Exception as exc:
        logger.debug("auth ensure_tables failed: %s", exc)
        return False


def _get_user_pg(email: str) -> dict | None:
    if not _ensure_tables():
        return None
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import AppUser

        with Session(get_sync_engine()) as session:
            rec = session.get(AppUser, email)
            if not rec:
                return None
            return {
                "email": rec.email,
                "password_hash": rec.password_hash,
                "role": rec.role or "user",
                "plan": rec.plan or "free",
            }
    except Exception as exc:
        logger.debug("auth PG get failed: %s", exc)
        return None


def _save_user_pg(email: str, password_hash: str, role: str = "user", plan: str = "free") -> bool:
    if not _ensure_tables():
        return False
    try:
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import AppUser

        with Session(get_sync_engine()) as session:
            if session.get(AppUser, email):
                raise ValueError("邮箱已注册")
            session.add(
                AppUser(
                    email=email,
                    password_hash=password_hash,
                    role=role,
                    plan=plan,
                    created_at=datetime.now(timezone.utc),
                )
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("邮箱已注册") from exc
        return True
    except ValueError:
        raise
    except Exception as exc:
        logger.debug("auth PG save failed: %s", exc)
        return False


def register_user(email: str, password: str, role: str = "user", plan: str = "free") -> None:
    email = email.strip().lower()
    if len(password) < _MIN_PASSWORD_LEN:
        raise ValueError(f"密码至少{_MIN_PASSWORD_LEN}位")
    if _get_user_pg(email) or email in _users_fallback:
        raise ValueError("邮箱已注册")
    ph = hash_password(password)
    if _save_user_pg(email, ph, role=role, plan=plan):
        _users_fallback[email] = {"email": email, "password_hash": ph, "role": role, "plan": plan}
        return
    if email in _users_fallback:
        raise ValueError("邮箱已注册")
    _users_fallback[email] = {"email": email, "password_hash": ph, "role": role, "plan": plan}
    logger.warning("auth user %s stored in memory only (PG unavailable)", email)


def authenticate_user(email: str, password: str) -> dict | None:
    email = email.strip().lower()
    user = _get_user_pg(email) or _users_fallback.get(email)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return {
        "email": user["email"],
        "role": user.get("role") or "user",
        "plan": user.get("plan") or "free",
    }


def create_access_token(email: str, role: str, plan: str = "free") -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {"sub": email, "role": role, "plan": plan, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    try:
        token = token.removeprefix("Bearer ").strip()
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload if payload.get("sub") else None
    except Exception:
        return None


def ensure_demo_user() -> None:
    email = (os.getenv("DEMO_USER_EMAIL") or "").strip().lower()
    password = os.getenv("DEMO_USER_PASSWORD") or ""
    if not email or len(password) < _MIN_PASSWORD_LEN:
        return
    if _get_user_pg(email) or email in _users_fallback:
        return
    try:
        register_user(email, password, role="admin", plan="subscriber")
        logger.info("demo user ensured: %s (role=admin)", email)
    except ValueError:
        pass
    except Exception as exc:
        logger.debug("ensure_demo_user: %s", exc)


def get_user_profile(email: str) -> dict | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    user = _get_user_pg(email) or _users_fallback.get(email)
    if not user:
        return None
    return {
        "email": user["email"],
        "role": user.get("role") or "user",
        "plan": user.get("plan") or "free",
    }


def issue_demo_login_token() -> dict | None:
    """DEMO_LOGIN_ENABLED 时为演示账号签发 token（不校验口令，口令不出前端）。"""
    if not DEMO_LOGIN_ENABLED:
        return None
    email = (os.getenv("DEMO_USER_EMAIL") or "").strip().lower()
    if not email:
        return None
    ensure_demo_user()
    profile = get_user_profile(email)
    if not profile:
        return None
    token = create_access_token(profile["email"], profile["role"], profile["plan"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": profile["role"],
        "plan": profile["plan"],
        "email": profile["email"],
    }
