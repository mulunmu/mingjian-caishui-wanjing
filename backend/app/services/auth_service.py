"""认证服务 — PostgreSQL 用户表 + 内存 L1；JWT"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

logger = logging.getLogger(__name__)

_DEV_JWT_SECRET = "risk-assessment-dev-jwt-do-not-use-in-prod"
# 无 compose/代码兜底签名钥：未设置时仅演示态临时使用 _DEV（启动校验会警告）
_JWT_FROM_ENV = (os.getenv("JWT_SECRET") or "").strip()
JWT_SECRET = _JWT_FROM_ENV or _DEV_JWT_SECRET
if not _JWT_FROM_ENV:
    logger.warning("JWT_SECRET unset; using fixed demo secret (set JWT_SECRET before any real deploy)")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

_users_fallback: dict[str, dict] = {}
_tables_ready = False

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "true").lower() == "true"
# 鉴权开启时默认关闭自助注册，避免任意人注册即获全站访问
ALLOW_SELF_REGISTER = os.getenv("ALLOW_SELF_REGISTER", "false").lower() == "true"
# 本地演示一键登录（不向前端下发口令）；AUTH_REQUIRED=true 时启动校验会拒绝
DEMO_LOGIN_ENABLED = os.getenv("DEMO_LOGIN_ENABLED", "false").lower() == "true"
_MIN_PASSWORD_LEN = 8 if AUTH_REQUIRED else 6


def validate_production_config() -> dict:
    """启动校验：JWT 密钥强度 + AUTH/CORS/演示登录组合；AUTH_REQUIRED=false 时仅拦截明显危险组合。"""
    auth_required = os.getenv("AUTH_REQUIRED", "true").lower() == "true"
    demo_login = os.getenv("DEMO_LOGIN_ENABLED", "false").lower() == "true"
    secret = (os.getenv("JWT_SECRET") or "").strip()
    cors = (os.getenv("CORS_ORIGINS") or "*").strip()
    errors: list[str] = []

    weak_secret = (not secret) or secret == _DEV_JWT_SECRET or len(secret) < 32
    if auth_required:
        if weak_secret:
            errors.append("AUTH_REQUIRED=true 时必须设置至少 32 字符的 JWT_SECRET（不得使用演示默认值）")
        if cors == "*" or not cors:
            errors.append("AUTH_REQUIRED=true 时 CORS_ORIGINS 不得为 *，需指定前端域名（逗号分隔）")
        if demo_login:
            localhost_only = bool(cors) and all(
                o.strip().startswith(("http://localhost", "http://127.0.0.1"))
                for o in cors.split(",")
                if o.strip()
            )
            if localhost_only:
                logger.warning(
                    "DEMO_LOGIN_ENABLED=true with AUTH_REQUIRED — local only; disable before public deploy"
                )
            else:
                errors.append(
                    "AUTH_REQUIRED=true 时不得开启 DEMO_LOGIN_ENABLED（无口令签发 admin token）；本地请将 CORS 限为 localhost"
                )
    elif weak_secret:
        # 演示态允许弱密钥，但写入 errors 供 health 可见；不阻断启动
        logger.warning("JWT_SECRET 未设置或为演示默认值；开启 AUTH_REQUIRED 前必须轮换")

    return {"ok": not errors, "auth_required": auth_required, "errors": errors}


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
                "pwd_ver": rec.pwd_ver or 0,
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


def _update_user_pg(email: str, *, role: str | None = None, plan: str | None = None) -> bool:
    """幂等升级既有用户（如演示账号早前以 free 落库 → 升级为 admin/subscriber）。"""
    if not _ensure_tables():
        return False
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import AppUser

        with Session(get_sync_engine()) as session:
            rec = session.get(AppUser, email)
            if not rec:
                return False
            if role is not None:
                rec.role = role
            if plan is not None:
                rec.plan = plan
            session.commit()
        return True
    except Exception as exc:
        logger.debug("auth PG update failed: %s", exc)
        return False


def register_user(email: str, password: str, role: str = "user", plan: str = "free") -> None:
    email = email.strip().lower()
    if len(password) < _MIN_PASSWORD_LEN:
        raise ValueError(f"密码至少{_MIN_PASSWORD_LEN}位")
    if _get_user_pg(email) or email in _users_fallback:
        raise ValueError("邮箱已注册")
    ph = hash_password(password)
    if _save_user_pg(email, ph, role=role, plan=plan):
        _users_fallback[email] = {
            "email": email,
            "password_hash": ph,
            "role": role,
            "plan": plan,
            "pwd_ver": 0,
        }
        return
    if email in _users_fallback:
        raise ValueError("邮箱已注册")
    _users_fallback[email] = {
        "email": email,
        "password_hash": ph,
        "role": role,
        "plan": plan,
        "pwd_ver": 0,
    }
    logger.warning("auth user %s stored in memory only (PG unavailable)", email)


def update_password(email: str, new_password: str) -> None:
    """重置密码：更新哈希并把 pwd_ver +1（使既有 JWT 立即失效）。

    仅用于已通过验证码校验的调用方 —— 本函数不做任何身份校验。
    失败抛 ValueError（中文）。
    """
    email = (email or "").strip().lower()
    if len(new_password or "") < _MIN_PASSWORD_LEN:
        raise ValueError(f"密码至少{_MIN_PASSWORD_LEN}位")

    ph = hash_password(new_password)

    def _update_pg() -> bool:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import AppUser

        with Session(get_sync_engine()) as session:
            rec = session.get(AppUser, email)
            if not rec:
                return False
            rec.password_hash = ph
            rec.pwd_ver = (rec.pwd_ver or 0) + 1
            session.commit()
        return True

    ok = False
    if _ensure_tables():
        try:
            ok = _update_pg()
        except Exception as exc:
            logger.debug("auth PG update_password failed: %s", exc)
            ok = False

    if email in _users_fallback:
        _users_fallback[email]["password_hash"] = ph
        _users_fallback[email]["pwd_ver"] = (_users_fallback[email].get("pwd_ver") or 0) + 1
        return

    if not ok:
        raise ValueError("账号不存在")


def get_user_pwd_ver(email: str) -> int | None:
    """读取当前 pwd_ver；用户不存在返回 None（用于 token 失效判定）。"""
    email = (email or "").strip().lower()
    if not email:
        return None
    user = _get_user_pg(email) or _users_fallback.get(email)
    if not user:
        return None
    return int(user.get("pwd_ver") or 0)


def verify_token_checked(token: str) -> dict | None:
    """在 verify_token 基础上校验 pwd_ver。

    仅当 token **携带** pwd_ver 声明时才查库比对；不带声明（旧签发路径 /
    单测直接构造的 token）视为不受此机制约束，保持既有行为。
    """
    payload = verify_token(token)
    if payload is None:
        return None
    if "pwd_ver" not in payload:
        return payload
    current = get_user_pwd_ver(str(payload.get("sub") or ""))
    if current is None:
        # 用户已不存在 —— 拒绝
        return None
    if int(payload.get("pwd_ver") or 0) != current:
        return None
    return payload


def authenticate_user(email: str, password: str) -> dict | None:
    email = email.strip().lower()
    user = _get_user_pg(email) or _users_fallback.get(email)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return {
        "email": user["email"],
        "role": user.get("role") or "user",
        "plan": user.get("plan") or "free",
        "pwd_ver": int(user.get("pwd_ver") or 0),
    }


def create_access_token(email: str, role: str, plan: str = "free", *, pwd_ver: int | None = None) -> str:
    """签发 JWT。

    `pwd_ver` 为 None 时不写入声明 —— 该 token 不受「改密失效」机制约束，
    用于兼容既有调用方（单测直接构造 token 的场景）。
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {"sub": email, "role": role, "plan": plan, "exp": expire}
    if pwd_ver is not None:
        payload["pwd_ver"] = int(pwd_ver)
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
    user = _get_user_pg(email)
    if user:
        # 幂等升级：演示账号须恒定 admin + subscriber，即便早前以 free 落库
        if user.get("role") != "admin" or user.get("plan") != "subscriber":
            _update_user_pg(email, role="admin", plan="subscriber")
            _users_fallback[email] = {
                "email": email,
                "password_hash": user.get("password_hash", ""),
                "role": "admin",
                "plan": "subscriber",
                "pwd_ver": user.get("pwd_ver") or 0,
            }
            logger.info("demo user upgraded: %s (role=admin, plan=subscriber)", email)
        return
    try:
        register_user(email, password, role="admin", plan="subscriber")
        logger.info("demo user ensured: %s (role=admin, plan=subscriber)", email)
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
        "pwd_ver": int(user.get("pwd_ver") or 0),
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
    token = create_access_token(
        profile["email"], profile["role"], profile["plan"], pwd_ver=profile.get("pwd_ver", 0)
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": profile["role"],
        "plan": profile["plan"],
        "email": profile["email"],
    }
