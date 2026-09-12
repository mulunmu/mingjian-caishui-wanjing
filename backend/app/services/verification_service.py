"""邮箱验证码服务 — 注册场景的一次性口令校验。

设计要点：
- 冷却期与每日配额全部落在 PG（`email_verification_codes` 表），不依赖 Redis，
  避免多 worker 下进程内计数失效。
- `consume_code` 用 SELECT ... FOR UPDATE 串行化，保证并发下同一个码
  不会通过两次校验。
- PG 不可用时回退内存字典（仅本地单进程演示；多 worker 下不保证一致性）。
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.db.urls import get_sync_engine
from app.models.verification import EmailVerificationCode, PasswordResetTicket
from app.services.auth_service import (
    JWT_ALGORITHM,
    JWT_SECRET,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

# ── 参数 ──
CODE_TTL_SECONDS = int(os.getenv("VERIFY_CODE_TTL", "300"))
RESEND_COOLDOWN_SECONDS = int(os.getenv("VERIFY_RESEND_COOLDOWN", "60"))
MAX_VERIFY_ATTEMPTS = int(os.getenv("VERIFY_MAX_ATTEMPTS", "5"))
DAILY_LIMIT_PER_EMAIL = int(os.getenv("VERIFY_DAILY_LIMIT_PER_EMAIL", "10"))
DAILY_LIMIT_PER_IP = int(os.getenv("VERIFY_DAILY_LIMIT_PER_IP", "30"))
CODE_LENGTH = 6
MAX_CODE_LENGTH = 10  # 硬限长，避免超长输入喂给 bcrypt

# 表单令牌：要求「停留在表单上」至少这么久才能发码，挡脚本裸打接口。
# 设为 0 可只验签名不验时长（误杀逃生阀）。
FORM_TOKEN_MIN_AGE = int(os.getenv("FORM_TOKEN_MIN_AGE_SECONDS", "2"))
FORM_TOKEN_TTL_SECONDS = int(os.getenv("FORM_TOKEN_TTL_SECONDS", "1800"))
FORM_TOKEN_TYP = "send_code"

# 重置密码票据
RESET_TICKET_TTL_SECONDS = int(os.getenv("RESET_TICKET_TTL_SECONDS", "600"))
RESET_TICKET_TYP = "pwd_reset"

# 注册门禁开关：默认关闭，保持既有注册流程逐字节不变
REQUIRE_EMAIL_VERIFICATION = (
    os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() in ("1", "true", "yes")
)

VALID_PURPOSES = ("register", "login", "reset")

# ── 内存回退（PG 不可用时）──
_codes_fallback: dict[tuple[str, str], dict] = {}
_tickets_fallback: dict[str, dict] = {}
_tables_ready = False


def _make_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def _ensure_tables() -> bool:
    global _tables_ready
    if _tables_ready:
        return True
    try:
        import app.models  # noqa: F401 — 注册模型
        from app.db.session import Base

        eng = get_sync_engine()
        Base.metadata.create_all(
            eng, tables=[EmailVerificationCode.__table__, PasswordResetTicket.__table__]
        )
        _tables_ready = True
        return True
    except Exception as exc:
        logger.debug("verification ensure_tables failed: %s", exc)
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    """PG 的 TIMESTAMPTZ 可能回传 naive datetime，比较前统一补 UTC。"""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _normalize(email: str, purpose: str) -> tuple[str, str]:
    email = (email or "").strip().lower()
    purpose = (purpose or "").strip().lower()
    if not email:
        raise ValueError("请输入邮箱")
    if purpose not in VALID_PURPOSES:
        raise ValueError("验证码用途不合法")
    return email, purpose


def _run(fn: Callable, *args, **kwargs):
    """执行 PG 路径。

    只有**基础设施故障**（连不上库）才降级到内存；业务规则拒绝（ValueError：
    冷却中 / 超配额 / 验证码错误）必须原样冒泡，否则会被静默降级成一个
    重新发码的 200，导致「用户收到的码」和「库里存的码」不一致。
    """
    if not _ensure_tables():
        return _UNAVAILABLE
    try:
        return fn(*args, **kwargs)
    except ValueError:
        raise
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("verification PG unavailable, fallback to memory: %s", exc)
        return _UNAVAILABLE


class _Unavailable:
    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return "<pg-unavailable>"


_UNAVAILABLE = _Unavailable()


# ──────────────────────────── 内存回退实现 ────────────────────────────


def _issue_memory(email: str, purpose: str, code_hash: str, now: datetime, client_ip: str | None) -> dict:
    key = (email, purpose)
    prev = _codes_fallback.get(key)
    if prev and (now - prev["created_at"]).total_seconds() < RESEND_COOLDOWN_SECONDS:
        wait = RESEND_COOLDOWN_SECONDS - int((now - prev["created_at"]).total_seconds())
        raise ValueError(f"验证码发送过于频繁，请 {max(wait, 1)} 秒后重试")
    _codes_fallback[key] = {
        "code_hash": code_hash,
        "expires_at": now + timedelta(seconds=CODE_TTL_SECONDS),
        "attempts": 0,
        "consumed_at": None,
        "created_at": now,
        "request_ip": client_ip,
    }
    return {"expires_in": CODE_TTL_SECONDS, "resend_after": RESEND_COOLDOWN_SECONDS}


# ──────────────────────────── PG 实现 ────────────────────────────


def _issue_pg(email: str, purpose: str, code_hash: str, now: datetime, client_ip: str | None) -> dict:
    from sqlalchemy.orm import Session

    with Session(get_sync_engine()) as session:
        # 冷却：只看尚未消费的最新一条
        last = session.execute(
            select(EmailVerificationCode.created_at)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        last_at = _as_aware(last)
        if last_at and (now - last_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
            wait = RESEND_COOLDOWN_SECONDS - int((now - last_at).total_seconds())
            raise ValueError(f"验证码发送过于频繁，请 {max(wait, 1)} 秒后重试")

        since = now - timedelta(days=1)
        # 按邮箱的日配额
        email_hits = session.execute(
            select(func.count())
            .select_from(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.created_at > since,
            )
        ).scalar_one()
        if email_hits >= DAILY_LIMIT_PER_EMAIL:
            raise ValueError("该邮箱今日验证码发送次数已达上限，请明天再试")

        # 按 IP 的日配额（request_ip 为空时跳过，避免误伤）
        if client_ip:
            ip_hits = session.execute(
                select(func.count())
                .select_from(EmailVerificationCode)
                .where(
                    EmailVerificationCode.request_ip == client_ip,
                    EmailVerificationCode.created_at > since,
                )
            ).scalar_one()
            if ip_hits >= DAILY_LIMIT_PER_IP:
                raise ValueError("当前网络今日验证码发送次数已达上限，请明天再试")

        # 旧码作废，保证同一时刻只有一个有效码
        session.execute(
            update(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        session.add(
            EmailVerificationCode(
                email=email,
                purpose=purpose,
                code_hash=code_hash,
                expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
                consumed_at=None,
                attempts=0,
                request_ip=client_ip,
                created_at=now,
            )
        )
        session.commit()
    return {"expires_in": CODE_TTL_SECONDS, "resend_after": RESEND_COOLDOWN_SECONDS}


def _consume_pg(email: str, purpose: str, code: str) -> None:
    from sqlalchemy.orm import Session

    now = _now()
    with Session(get_sync_engine()) as session:
        rec = session.execute(
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.consumed_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
            .with_for_update()
        ).scalar_one_or_none()

        if rec is None:
            raise ValueError("验证码已失效，请重新获取")
        if _as_aware(rec.expires_at) < now:
            raise ValueError("验证码已过期，请重新获取")
        if rec.attempts >= MAX_VERIFY_ATTEMPTS:
            raise ValueError("验证码错误次数过多，请重新获取")

        if not verify_password(code, rec.code_hash):
            rec.attempts += 1
            session.commit()
            raise ValueError("验证码错误")

        rec.consumed_at = now
        session.commit()


def _consume_memory(email: str, purpose: str, code: str) -> None:
    now = _now()
    rec = _codes_fallback.get((email, purpose))
    if rec is None or rec["consumed_at"] is not None:
        raise ValueError("验证码已失效，请重新获取")
    if rec["expires_at"] < now:
        raise ValueError("验证码已过期，请重新获取")
    if rec["attempts"] >= MAX_VERIFY_ATTEMPTS:
        raise ValueError("验证码错误次数过多，请重新获取")
    if not verify_password(code, rec["code_hash"]):
        rec["attempts"] += 1
        raise ValueError("验证码错误")
    rec["consumed_at"] = now


# ──────────────────────────── 对外接口 ────────────────────────────


def issue_code(email: str, purpose: str, *, client_ip: str | None = None) -> dict:
    """生成并落库验证码（调用方负责发送邮件）。返回 {expires_in, resend_after}。

    失败抛 ValueError（中文文案，可直接回给用户）。
    """
    email, purpose = _normalize(email, purpose)
    code = _make_code()
    code_hash = hash_password(code)
    now = _now()

    out = _run(_issue_pg, email, purpose, code_hash, now, client_ip)
    if out is _UNAVAILABLE:
        out = _issue_memory(email, purpose, code_hash, now, client_ip)

    out["code"] = code  # 调用方发送后应立即丢弃，勿写日志
    return out


def consume_code(email: str, purpose: str, code: str) -> None:
    """校验并消费验证码；任何失败抛 ValueError（中文文案）。"""
    email, purpose = _normalize(email, purpose)
    code = (code or "").strip()
    if not code:
        raise ValueError("请输入验证码")
    if len(code) > MAX_CODE_LENGTH:
        raise ValueError("验证码错误")

    out = _run(_consume_pg, email, purpose, code)
    if out is _UNAVAILABLE:
        _consume_memory(email, purpose, code)


def clear_memory_store() -> None:
    """仅供单测重置内存回退。"""
    _codes_fallback.clear()
    _tickets_fallback.clear()


# ──────────────────────────── 表单令牌（防机器）────────────────────────────
#
# 无状态签名时间戳：不落库、不进 Redis。
# 故意不写 `sub` —— auth_service.verify_token() 只认带 sub 的 payload，
# 因此这个 token 无法被当成登录凭证使用。


def issue_form_token() -> dict:
    """签发表单令牌（供前端在打开注册表单时获取一次）。"""
    from jose import jwt

    now = int(_now().timestamp())
    payload = {
        "typ": FORM_TOKEN_TYP,
        "iat": now,
        "exp": now + FORM_TOKEN_TTL_SECONDS,
    }
    return {
        "token": jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM),
        "min_age": FORM_TOKEN_MIN_AGE,
        "expires_in": FORM_TOKEN_TTL_SECONDS,
    }


def check_form_token(token: str) -> None:
    """校验表单令牌；失败抛 ValueError（中文文案）。"""
    from jose import JWTError, jwt

    token = (token or "").strip()
    if not token:
        raise ValueError("请求来源校验失败，请刷新页面后重试")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        logger.debug("form_token decode failed: %s", exc)
        raise ValueError("请求来源校验已过期，请刷新页面后重试") from exc

    if payload.get("typ") != FORM_TOKEN_TYP:
        raise ValueError("请求来源校验失败，请刷新页面后重试")

    iat = payload.get("iat")
    if not isinstance(iat, int):
        raise ValueError("请求来源校验失败，请刷新页面后重试")

    if FORM_TOKEN_MIN_AGE > 0:
        age = int(_now().timestamp()) - iat
        if age < FORM_TOKEN_MIN_AGE:
            raise ValueError("操作过快，请稍后重试")


# ──────────────────── 重置密码票据（一次性）────────────────────
#
# 为什么需要它：`/reset-password` 若只校验「验证码正确」，那么任何知道
# 目标邮箱的人都能改掉别人密码 —— 因为验证码是发给邮箱持有者的，
# 但接口本身无法区分「谁在调用」。票据把「验证码已通过」这个事实
# 变成一个只能消费一次、且与邮箱绑定的凭证。


def _ticket_memory_store() -> dict[str, dict]:
    return _tickets_fallback


def _issue_ticket_pg(jti: str, email: str, now: datetime) -> None:
    from sqlalchemy.orm import Session

    with Session(get_sync_engine()) as session:
        session.add(
            PasswordResetTicket(
                jti=jti,
                email=email,
                expires_at=now + timedelta(seconds=RESET_TICKET_TTL_SECONDS),
                consumed_at=None,
                created_at=now,
            )
        )
        session.commit()


def _consume_ticket_pg(jti: str) -> str | None:
    """原子消费：UPDATE ... WHERE consumed_at IS NULL，rowcount==1 才算拿到。"""
    from sqlalchemy.orm import Session

    now = _now()
    with Session(get_sync_engine()) as session:
        rec = session.get(PasswordResetTicket, jti)
        if rec is None:
            return None
        if _as_aware(rec.expires_at) < now:
            return None
        result = session.execute(
            update(PasswordResetTicket)
            .where(
                PasswordResetTicket.jti == jti,
                PasswordResetTicket.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        session.commit()
        if result.rowcount != 1:
            return None
        return rec.email


def issue_reset_ticket(email: str) -> dict:
    """签发一次性重置票据（调用方须已校验验证码）。"""
    from jose import jwt

    email = (email or "").strip().lower()
    if not email:
        raise ValueError("请输入邮箱")
    now = _now()
    jti = secrets.token_urlsafe(32)[:64]
    expires_at = now + timedelta(seconds=RESET_TICKET_TTL_SECONDS)

    out = _run(_issue_ticket_pg, jti, email, now)
    if out is _UNAVAILABLE:
        _tickets_fallback[jti] = {"email": email, "expires_at": expires_at, "consumed_at": None}

    token = jwt.encode(
        {
            "typ": RESET_TICKET_TYP,
            "sub": email,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return {"reset_token": token, "expires_in": RESET_TICKET_TTL_SECONDS}


def consume_reset_ticket(token: str) -> str:
    """校验并消费重置票据；返回邮箱。任何失败抛 ValueError（中文）。"""
    from jose import JWTError, jwt

    token = (token or "").strip()
    if not token:
        raise ValueError("重置凭证缺失，请重新验证邮箱")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        logger.debug("reset ticket decode failed: %s", exc)
        raise ValueError("重置凭证已过期，请重新验证邮箱") from exc

    if payload.get("typ") != RESET_TICKET_TYP:
        raise ValueError("重置凭证无效，请重新验证邮箱")

    jti = str(payload.get("jti") or "")
    email = str(payload.get("sub") or "").strip().lower()
    if not jti or not email:
        raise ValueError("重置凭证无效，请重新验证邮箱")

    now = _now()
    out = _run(_consume_ticket_pg, jti)
    if out is _UNAVAILABLE:
        rec = _tickets_fallback.get(jti)
        if rec is None or rec["consumed_at"] is not None or rec["expires_at"] < now:
            raise ValueError("重置凭证已失效，请重新验证邮箱")
        rec["consumed_at"] = now
        return rec["email"]

    if not out:
        raise ValueError("重置凭证已失效，请重新验证邮箱")
    return out
