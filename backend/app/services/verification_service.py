"""邮箱验证码服务 — 一次性口令校验（对齐《邮件功能企划书》§3.2）。

设计要点（§3.2）：
- **TTL 按用途**：register=15min；login/send_email/bind_email=10min（reset 归入 10min）。
- **限流**：每邮箱 15 分钟 ≤5 次发送请求（滑动窗口）+ 每 IP 可配上限；
  重发冷却 60s 独立于限流。
- **试错上限 5 次**：失败计数用**独立键** `otp_attempts:{email}:{purpose}`（独立
  15min TTL），与「码」分离；超限即作废该码并进入冷却。
- **存储**：Redis 优先 / PG 降级 / 内存兜底（复用 `REDIS_URL` 探测模式）。
  Redis 分支用 `SET + TTL` 保「同邮箱同用途单码」，消费走 compare-and-delete
  的 Lua 脚本保一次性；PG 分支沿用 `EmailVerificationCode`（`SELECT ... FOR
  UPDATE` 串行化）；内存分支仅本地单进程演示。
- 码为 `secrets` 生成 6 位数字，哈希（bcrypt）落库，码不进日志。
"""
from __future__ import annotations

import logging
import os
import secrets
import time
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

# ── 参数（§3.2）──
CODE_LENGTH = 6
MAX_CODE_LENGTH = 10  # 硬限长，避免超长输入喂给 bcrypt
RESEND_COOLDOWN_SECONDS = int(os.getenv("VERIFY_RESEND_COOLDOWN", "60"))
MAX_VERIFY_ATTEMPTS = int(os.getenv("VERIFY_MAX_ATTEMPTS", "5"))

# TTL 按用途：register 15min；login/send_email/bind_email 10min（§3.2(1)）
_TTL_REGISTER = int(os.getenv("VERIFY_CODE_TTL_REGISTER", "900"))
_TTL_OTHER = int(os.getenv("VERIFY_CODE_TTL_LOGIN", "600"))
CODE_TTL_SECONDS: dict[str, int] = {
    "register": _TTL_REGISTER,
    "login": _TTL_OTHER,
    "send_email": _TTL_OTHER,
    "bind_email": _TTL_OTHER,
    "reset": _TTL_OTHER,
}

# 限流：每邮箱 15 分钟 ≤5 次发送请求（§3.2(6)）；每 IP 可配
SEND_WINDOW_SECONDS = int(os.getenv("VERIFY_SEND_WINDOW_SECONDS", "900"))
SEND_LIMIT_PER_EMAIL = int(os.getenv("VERIFY_SEND_LIMIT_PER_EMAIL", "5"))
SEND_LIMIT_PER_IP = int(os.getenv("VERIFY_SEND_LIMIT_PER_IP", "20"))
# 试错超限后的冷却窗口（独立 attempts 计数键的 TTL，§3.2(3)）
ATTEMPT_WINDOW_SECONDS = int(os.getenv("VERIFY_ATTEMPT_WINDOW_SECONDS", "900"))

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

VALID_PURPOSES = ("register", "login", "send_email", "bind_email", "reset")


def _code_ttl(purpose: str) -> int:
    return CODE_TTL_SECONDS.get(purpose, _TTL_OTHER)


# ── Redis（优先）──
_redis = None
_redis_checked = False


def _get_redis():
    """REDIS_URL 探测：可用才返回 client，否则 None（与 rate_limiter 同口径）。"""
    global _redis, _redis_checked
    if _redis_checked:
        return _redis
    _redis_checked = True
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        _redis = client
        logger.info("verification_service using Redis")
    except Exception as exc:
        logger.warning("REDIS_URL set but unavailable (%s); PG/memory fallback", exc)
        _redis = None
    return _redis


def _safe_key(value: str) -> str:
    raw = (value or "").strip()[:128] or "anon"
    return "".join(c if c.isalnum() or c in "._-:@" else "_" for c in raw)


_GETDEL_IF_EQUAL = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


# ── 内存回退（PG 不可用时）──
_codes_fallback: dict[tuple[str, str], dict] = {}
_tickets_fallback: dict[str, dict] = {}
_send_window_fallback: dict[str, list[float]] = {}
_send_ip_window_fallback: dict[str, list[float]] = {}
_blocked_fallback: dict[tuple[str, str], float] = {}
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


# ──────────────────────────── Redis 实现 ────────────────────────────


def _send_card(r, key: str, cutoff: float) -> int:
    """滑动窗口计数：先清过期成员再取基数。"""
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, cutoff)
    pipe.zcard(key)
    pipe.expire(key, SEND_WINDOW_SECONDS + 60)
    res = pipe.execute()
    return int(res[1] or 0)


def _send_record(r, key: str, now: float) -> None:
    member = f"{now:.6f}:{secrets.token_hex(4)}"
    pipe = r.pipeline()
    pipe.zadd(key, {member: now})
    pipe.zremrangebyscore(key, 0, now - SEND_WINDOW_SECONDS)
    pipe.expire(key, SEND_WINDOW_SECONDS + 60)
    pipe.execute()


def _issue_redis(r, email: str, purpose: str, code_hash: str, client_ip: str | None) -> dict:
    now = time.time()
    att_key = f"otp_attempts:{email}:{purpose}"

    # 试错超限冷却（§3.2(3)）：计数与码分离
    if int(r.get(att_key) or 0) >= MAX_VERIFY_ATTEMPTS:
        raise ValueError("验证码错误次数过多，请稍后重试")

    # 每邮箱 15 分钟 ≤5 次（§3.2(6)）
    send_key = f"otp_send:{email}"
    if _send_card(r, send_key, now - SEND_WINDOW_SECONDS) >= SEND_LIMIT_PER_EMAIL:
        raise ValueError("验证码发送过于频繁，请稍后重试")
    if client_ip:
        ip_key = f"otp_sendip:{_safe_key(client_ip)}"
        if _send_card(r, ip_key, now - SEND_WINDOW_SECONDS) >= SEND_LIMIT_PER_IP:
            raise ValueError("当前网络验证码发送过于频繁，请稍后重试")

    # 重发冷却 60s
    last_key = f"otp_last:{email}:{purpose}"
    if not r.set(last_key, "1", nx=True, ex=RESEND_COOLDOWN_SECONDS):
        wait = max(int(r.ttl(last_key) or 0), 1)
        raise ValueError(f"验证码发送过于频繁，请 {wait} 秒后重试")

    # 存码：覆盖旧码，保证同一时刻只有一个有效码（§3.2 单码）
    code_key = f"otp:{email}:{purpose}"
    r.set(code_key, code_hash, ex=_code_ttl(purpose))
    _send_record(r, send_key, now)
    if client_ip:
        _send_record(r, ip_key, now)
    r.delete(att_key)  # 新码重置试错计数
    return {"expires_in": _code_ttl(purpose), "resend_after": RESEND_COOLDOWN_SECONDS}


def _consume_redis(r, email: str, purpose: str, code: str) -> None:
    att_key = f"otp_attempts:{email}:{purpose}"
    if int(r.get(att_key) or 0) >= MAX_VERIFY_ATTEMPTS:
        raise ValueError("验证码错误次数过多，请重新获取")

    code_key = f"otp:{email}:{purpose}"
    stored = r.get(code_key)
    if not stored:
        raise ValueError("验证码已失效，请重新获取")

    if not verify_password(code, stored):
        n = int(r.incr(att_key) or 0)
        if n == 1:
            r.expire(att_key, ATTEMPT_WINDOW_SECONDS)
        if n >= MAX_VERIFY_ATTEMPTS:
            r.delete(code_key)  # 作废（§3.2(3)）
            r.expire(att_key, ATTEMPT_WINDOW_SECONDS)
        raise ValueError("验证码错误")

    # 一次性：compare-and-delete，并发下仅一个请求能删成功
    if int(r.eval(_GETDEL_IF_EQUAL, 1, code_key, stored)) != 1:
        raise ValueError("验证码已失效，请重新获取")
    r.delete(att_key)


# ──────────────────────────── 内存回退实现 ────────────────────────────


def _prune(bucket: list[float], cutoff: float) -> None:
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)


def _issue_memory(email: str, purpose: str, code_hash: str, now: datetime, client_ip: str | None) -> dict:
    key = (email, purpose)
    now_ts = now.timestamp()

    # 试错超限冷却
    blocked_until = _blocked_fallback.get(key)
    if blocked_until and blocked_until > now_ts:
        wait = int(blocked_until - now_ts) + 1
        raise ValueError(f"验证码错误次数过多，请 {wait} 秒后重试")

    # 每邮箱限流（15 分钟窗口）
    email_bucket = _send_window_fallback.setdefault(email, [])
    _prune(email_bucket, now_ts - SEND_WINDOW_SECONDS)
    if len(email_bucket) >= SEND_LIMIT_PER_EMAIL:
        raise ValueError("验证码发送过于频繁，请稍后重试")
    if client_ip:
        ip_bucket = _send_ip_window_fallback.setdefault(client_ip, [])
        _prune(ip_bucket, now_ts - SEND_WINDOW_SECONDS)
        if len(ip_bucket) >= SEND_LIMIT_PER_IP:
            raise ValueError("当前网络验证码发送过于频繁，请稍后重试")

    # 重发冷却
    prev = _codes_fallback.get(key)
    if prev and (now - prev["created_at"]).total_seconds() < RESEND_COOLDOWN_SECONDS:
        wait = RESEND_COOLDOWN_SECONDS - int((now - prev["created_at"]).total_seconds())
        raise ValueError(f"验证码发送过于频繁，请 {max(wait, 1)} 秒后重试")

    _codes_fallback[key] = {
        "code_hash": code_hash,
        "expires_at": now + timedelta(seconds=_code_ttl(purpose)),
        "attempts": 0,
        "consumed_at": None,
        "created_at": now,
        "request_ip": client_ip,
    }
    email_bucket.append(now_ts)
    if client_ip:
        ip_bucket.append(now_ts)
    return {"expires_in": _code_ttl(purpose), "resend_after": RESEND_COOLDOWN_SECONDS}


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
        if rec["attempts"] >= MAX_VERIFY_ATTEMPTS:
            # 计数与码分离的等价物：超限即进入 15 分钟冷却（码由 attempts 守卫阻断使用）
            _blocked_fallback[(email, purpose)] = (
                now + timedelta(seconds=ATTEMPT_WINDOW_SECONDS)
            ).timestamp()
        raise ValueError("验证码错误")
    rec["consumed_at"] = now
    _blocked_fallback.pop((email, purpose), None)


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

        # 试错超限冷却（计数与码分离：最近窗口内有过超限记录则拒绝重发）
        failed = session.execute(
            select(func.count())
            .select_from(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.attempts >= MAX_VERIFY_ATTEMPTS,
                EmailVerificationCode.created_at > now - timedelta(seconds=ATTEMPT_WINDOW_SECONDS),
            )
        ).scalar_one()
        if failed > 0:
            raise ValueError("验证码错误次数过多，请稍后重试")

        since = now - timedelta(seconds=SEND_WINDOW_SECONDS)
        # 每邮箱 15 分钟 ≤5 次（§3.2(6)）
        email_hits = session.execute(
            select(func.count())
            .select_from(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.created_at > since,
            )
        ).scalar_one()
        if email_hits >= SEND_LIMIT_PER_EMAIL:
            raise ValueError("验证码发送过于频繁，请稍后重试")

        # 按 IP 的窗口配额（request_ip 为空时跳过，避免误伤）
        if client_ip:
            ip_hits = session.execute(
                select(func.count())
                .select_from(EmailVerificationCode)
                .where(
                    EmailVerificationCode.request_ip == client_ip,
                    EmailVerificationCode.created_at > since,
                )
            ).scalar_one()
            if ip_hits >= SEND_LIMIT_PER_IP:
                raise ValueError("当前网络验证码发送过于频繁，请稍后重试")

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
                expires_at=now + timedelta(seconds=_code_ttl(purpose)),
                consumed_at=None,
                attempts=0,
                request_ip=client_ip,
                created_at=now,
            )
        )
        session.commit()
    return {"expires_in": _code_ttl(purpose), "resend_after": RESEND_COOLDOWN_SECONDS}


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
            if rec.attempts >= MAX_VERIFY_ATTEMPTS:
                rec.consumed_at = now  # 超限作废（§3.2(3)）
            session.commit()
            raise ValueError("验证码错误")

        rec.consumed_at = now
        session.commit()


# ──────────────────────────── 对外接口 ────────────────────────────


def issue_code(email: str, purpose: str, *, client_ip: str | None = None) -> dict:
    """生成并落库验证码（调用方负责发送邮件）。返回 {expires_in, resend_after, code}。

    失败抛 ValueError（中文文案，可直接回给用户）。Redis 优先 / PG 降级 / 内存兜底。
    """
    email, purpose = _normalize(email, purpose)
    code = _make_code()
    code_hash = hash_password(code)

    r = _get_redis()
    if r is not None:
        try:
            out = _issue_redis(r, email, purpose, code_hash, client_ip)
            out["code"] = code
            return out
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("verification Redis issue failed (%s); PG/memory fallback", exc)

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

    r = _get_redis()
    if r is not None:
        try:
            _consume_redis(r, email, purpose, code)
            return
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("verification Redis consume failed (%s); PG/memory fallback", exc)

    out = _run(_consume_pg, email, purpose, code)
    if out is _UNAVAILABLE:
        _consume_memory(email, purpose, code)


def clear_memory_store() -> None:
    """仅供单测重置内存回退。"""
    _codes_fallback.clear()
    _tickets_fallback.clear()
    _send_window_fallback.clear()
    _send_ip_window_fallback.clear()
    _blocked_fallback.clear()


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
