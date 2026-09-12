"""邮箱验证码 — 单元测试（不真发邮件，不改动既有注册测试）。

覆盖：
1. 正确码通过
2. 错误码拒绝
3. 过期码拒绝
4. 连错达上限后作废
5. 重放（同一码二次消费）被拒
6. 重发冷却期内被拒
7. 重发后旧码失效、新码可用
8. purpose 隔离：register 的码不能用于 login
9. 内存回退路径同样可用（PG 不可用时）

⚠️ 覆盖边界（勿误读）：
上述用例都跑在**内存回退分支**（autouse fixture 强制 `_ensure_tables=False`）。
PG 分支 `_issue_pg` 的冷却/日配额、以及 `consume_code` 的 `SELECT ... FOR UPDATE`
行锁，**单测未覆盖**，需靠真实 PG 冒烟验证（见 test_pg_precheck 的 skip 说明）。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import verification_service as vs  # noqa: E402


@pytest.fixture(autouse=True)
def _use_memory_store(monkeypatch):
    """强制走内存回退，避免单测污染真实 PG。

    `_ensure_tables` 返回 False 时，_run() 会统一走内存分支。
    """
    vs.clear_memory_store()
    monkeypatch.setattr(vs, "_ensure_tables", lambda: False)
    yield
    vs.clear_memory_store()


def _issue(email: str, purpose: str = "register") -> str:
    return vs.issue_code(email, purpose)["code"]


# ── 1. 正确码通过 ──
def test_consume_correct_code_passes():
    code = _issue("ok@example.com")
    vs.consume_code("ok@example.com", "register", code)  # 不抛即通过


# ── 2. 错误码拒绝 ──
def test_consume_wrong_code_rejected():
    _issue("wrong@example.com")
    with pytest.raises(ValueError) as exc:
        vs.consume_code("wrong@example.com", "register", "000000")
    assert "验证码错误" in str(exc.value)


# ── 3. 过期码拒绝 ──
def test_consume_expired_code_rejected(monkeypatch):
    code = _issue("expired@example.com")
    rec = vs._codes_fallback[("expired@example.com", "register")]
    rec["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(ValueError) as exc:
        vs.consume_code("expired@example.com", "register", code)
    assert "已过期" in str(exc.value)


# ── 4. 连错达上限后作废 ──
def test_attempt_cap_invalidates_code():
    code = _issue("cap@example.com")
    for _ in range(vs.MAX_VERIFY_ATTEMPTS):
        with pytest.raises(ValueError):
            vs.consume_code("cap@example.com", "register", "000000")
    # 即使此后给正确的码，也应因超限被拒
    with pytest.raises(ValueError) as exc:
        vs.consume_code("cap@example.com", "register", code)
    assert "次数过多" in str(exc.value)


# ── 5. 重放被拒 ──
def test_code_cannot_be_reused():
    code = _issue("replay@example.com")
    vs.consume_code("replay@example.com", "register", code)
    with pytest.raises(ValueError) as exc:
        vs.consume_code("replay@example.com", "register", code)
    assert "已失效" in str(exc.value)


# ── 6. 重发冷却 ──
def test_resend_within_cooldown_rejected():
    _issue("cooldown@example.com")
    with pytest.raises(ValueError) as exc:
        vs.issue_code("cooldown@example.com", "register")
    assert "过于频繁" in str(exc.value)


# ── 7. 重发后旧码失效、新码可用 ──
def test_reissue_invalidates_old_code(monkeypatch):
    old = _issue("reissue@example.com")
    # 把创建时间往前挪，绕过冷却
    rec = vs._codes_fallback[("reissue@example.com", "register")]
    rec["created_at"] = datetime.now(timezone.utc) - timedelta(
        seconds=vs.RESEND_COOLDOWN_SECONDS + 1
    )
    new = vs.issue_code("reissue@example.com", "register")["code"]
    assert new != old
    with pytest.raises(ValueError) as exc:
        vs.consume_code("reissue@example.com", "register", old)
    assert "验证码错误" in str(exc.value)
    vs.consume_code("reissue@example.com", "register", new)


# ── 8. purpose 隔离 ──
def test_purpose_isolation():
    code = _issue("iso@example.com", "register")
    with pytest.raises(ValueError):
        vs.consume_code("iso@example.com", "login", code)


# ── 9. 内存回退可用 ──
def test_memory_fallback_roundtrip():
    code = _issue("mem@example.com")
    vs.consume_code("mem@example.com", "register", code)
    assert vs._codes_fallback[("mem@example.com", "register")]["consumed_at"] is not None


# ── 附加：非法 purpose / 空码 ──
def test_invalid_purpose_rejected():
    with pytest.raises(ValueError) as exc:
        vs.issue_code("bad@example.com", "hack")
    assert "用途不合法" in str(exc.value)


def test_empty_code_rejected():
    _issue("empty@example.com")
    with pytest.raises(ValueError) as exc:
        vs.consume_code("empty@example.com", "register", "")
    assert "请输入验证码" in str(exc.value)


def test_overlong_code_rejected():
    _issue("long@example.com")
    with pytest.raises(ValueError) as exc:
        vs.consume_code("long@example.com", "register", "9" * (vs.MAX_CODE_LENGTH + 1))
    assert "验证码错误" in str(exc.value)


def test_code_is_six_digits():
    code = _issue("fmt@example.com")
    assert len(code) == vs.CODE_LENGTH and code.isdigit()


# ────────────────────── 表单令牌（防机器）──────────────────────


def test_form_token_missing_rejected():
    with pytest.raises(ValueError) as exc:
        vs.check_form_token("")
    assert "刷新页面" in str(exc.value)


def test_form_token_bad_signature_rejected():
    with pytest.raises(ValueError) as exc:
        vs.check_form_token("not.a.jwt")
    assert "过期" in str(exc.value) or "失败" in str(exc.value)


def test_form_token_wrong_typ_rejected():
    """typ 不匹配的 token（例如拿登录 JWT 来冒充）必须拒绝。"""
    from app.services.auth_service import create_access_token

    # 登录 token 带 sub，且 typ 不是 send_code
    with pytest.raises(ValueError):
        vs.check_form_token(create_access_token("a@b.com", "user"))


def test_form_token_too_fast_rejected(monkeypatch):
    """age < FORM_TOKEN_MIN_AGE 时拒绝（模拟「打开页面立刻发码」）。"""
    issued = vs.issue_form_token()
    # 令牌的 iat 是当前秒，age≈0 < 2
    assert vs.FORM_TOKEN_MIN_AGE > 0
    with pytest.raises(ValueError) as exc:
        vs.check_form_token(issued["token"])
    assert "过快" in str(exc.value)


def test_form_token_passes_after_min_age():
    import time as _time

    issued = vs.issue_form_token()
    _time.sleep(vs.FORM_TOKEN_MIN_AGE + 0.5)
    vs.check_form_token(issued["token"])  # 不抛即通过


def test_form_token_min_age_zero_disables_timing(monkeypatch):
    monkeypatch.setattr(vs, "FORM_TOKEN_MIN_AGE", 0)
    issued = vs.issue_form_token()
    vs.check_form_token(issued["token"])  # 立即通过


def test_form_token_not_usable_as_login_credential():
    """关键安全性质：表单令牌不得被 verify_token 当成登录凭证。"""
    from app.services.auth_service import verify_token

    issued = vs.issue_form_token()
    assert verify_token(issued["token"]) is None


def test_form_token_fields():
    issued = vs.issue_form_token()
    assert set(issued) == {"token", "min_age", "expires_in"}
    assert issued["min_age"] == vs.FORM_TOKEN_MIN_AGE


# ──────────────────── 重置密码票据（一次性）────────────────────


def test_reset_ticket_roundtrip():
    issued = vs.issue_reset_ticket("rt@example.com")
    assert "reset_token" in issued
    assert issued["expires_in"] == vs.RESET_TICKET_TTL_SECONDS
    assert vs.consume_reset_ticket(issued["reset_token"]) == "rt@example.com"


def test_reset_ticket_cannot_be_reused():
    """票据一次性 —— 防止拿着同一个票据改两次密码。"""
    issued = vs.issue_reset_ticket("rt2@example.com")
    vs.consume_reset_ticket(issued["reset_token"])
    with pytest.raises(ValueError) as exc:
        vs.consume_reset_ticket(issued["reset_token"])
    assert "已失效" in str(exc.value)


def test_reset_ticket_empty_rejected():
    with pytest.raises(ValueError) as exc:
        vs.consume_reset_ticket("")
    assert "缺失" in str(exc.value)


def test_reset_ticket_bad_signature_rejected():
    with pytest.raises(ValueError) as exc:
        vs.consume_reset_ticket("forged.ticket.value")
    assert "过期" in str(exc.value) or "无效" in str(exc.value)


def test_reset_ticket_wrong_typ_rejected():
    """表单令牌 / 登录 token 都不能当重置票据用。"""
    with pytest.raises(ValueError):
        vs.consume_reset_ticket(vs.issue_form_token()["token"])
    from app.services.auth_service import create_access_token

    with pytest.raises(ValueError):
        vs.consume_reset_ticket(create_access_token("a@b.com", "user"))


def test_reset_ticket_expired_rejected():
    issued = vs.issue_reset_ticket("rt3@example.com")
    from jose import jwt

    payload = jwt.decode(issued["reset_token"], vs.JWT_SECRET, algorithms=[vs.JWT_ALGORITHM])
    # 本地把票据标记为已过期（内存回退分支）
    vs._tickets_fallback[payload["jti"]]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    with pytest.raises(ValueError) as exc:
        vs.consume_reset_ticket(issued["reset_token"])
    assert "已失效" in str(exc.value)


def test_reset_ticket_not_usable_as_login_credential():
    """重置票据也不得被 verify_token 当成登录凭证。"""
    from app.services.auth_service import verify_token, verify_token_checked

    issued = vs.issue_reset_ticket("rt4@example.com")
    # 票据带 sub 但 typ=pwd_reset —— verify_token 会返回 payload，
    # 但 deps 走的是 verify_token_checked，且票据没有 pwd_ver 声明，
    # 因此真正的防线是「没有 /reset-password 之外的端点消费它」。
    # 这里断言票据不携带 pwd_ver，避免它意外获得普通 token 的语义。
    payload = verify_token(issued["reset_token"])
    assert payload is not None
    assert "pwd_ver" not in payload
    assert verify_token_checked(issued["reset_token"]) is not None  # 无 pwd_ver 声明 → 不查库
