import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from app.api.deps import get_current_user_optional
from app.responses import UTF8JSONResponse
from app.services import auth_service, email_service, trusted_email_service, verification_service
from app.services.sync_runner import run_blocking

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    """与 main._client_key_from_scope 同口径：默认用直连 peer，TRUST_PROXY=true 才信 XFF。"""
    if os.getenv("TRUST_PROXY", "false").lower() in ("1", "true", "yes"):
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            return forwarded[:64]
    return request.client.host if request.client else None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    # 邮箱验证码：REQUIRE_EMAIL_VERIFICATION=false 时可省略（保持既有调用方不变）；
    # 一旦携带则必须正确。
    code: str | None = None


class SendCodeRequest(BaseModel):
    email: EmailStr
    purpose: Literal["register", "login", "send_email", "bind_email", "reset"] = "register"
    # 表单令牌：由 GET /auth/form-token 获取，用于挡裸打接口的脚本
    form_token: str | None = None


class LoginByCodeRequest(BaseModel):
    email: EmailStr
    code: str


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    purpose: Literal["send_email", "bind_email"] = "send_email"
    code: str
    remember: bool = False


class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_class=UTF8JSONResponse)
async def login(body: LoginRequest):
    user = await run_blocking(auth_service.authenticate_user, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = auth_service.create_access_token(
        user["email"], user["role"], user["plan"], pwd_ver=user.get("pwd_ver", 0)
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "plan": user["plan"],
    }


@router.post("/login-by-code", response_class=UTF8JSONResponse)
async def login_by_code(body: LoginByCodeRequest):
    """验证码登录：一次性验证码校验通过即签发 JWT。"""
    email = body.email.strip().lower()
    try:
        await run_blocking(verification_service.consume_code, email, "login", body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = auth_service.get_user_profile(email)
    if not user:
        raise HTTPException(status_code=404, detail="该邮箱尚未注册，请先注册")
    token = auth_service.create_access_token(
        user["email"], user["role"], user["plan"], pwd_ver=user.get("pwd_ver", 0)
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "plan": user["plan"],
    }


@router.post("/verify-code", response_class=UTF8JSONResponse)
async def verify_code(
    body: VerifyCodeRequest,
    _user: dict | None = Depends(get_current_user_optional),
):
    """受信邮箱验证：校验验证码；bind_email 或勾选「记住」时登记受信邮箱。"""
    email = body.email.strip().lower()
    try:
        await run_blocking(verification_service.consume_code, email, body.purpose, body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    owner = (_user or {}).get("sub") or (_user or {}).get("email")
    if body.purpose == "bind_email":
        if not owner:
            raise HTTPException(status_code=401, detail="请先登录")
        await run_blocking(trusted_email_service.add_trusted_email, owner, email, "verified")
    elif body.remember and owner:
        await run_blocking(trusted_email_service.add_trusted_email, owner, email, "verified")

    trusted = bool(owner) and (body.purpose == "bind_email" or body.remember)
    return {"message": "验证通过", "email": email, "trusted": trusted}


@router.get("/form-token", response_class=UTF8JSONResponse)
async def form_token():
    """签发防机器用的表单令牌（前端打开注册表单时取一次）。"""
    return verification_service.issue_form_token()


@router.post("/send-code", response_class=UTF8JSONResponse)
async def send_code(body: SendCodeRequest, request: Request):
    """发送邮箱验证码（注册/登录共用）。"""
    if not email_service.is_configured():
        raise HTTPException(status_code=503, detail=email_service.NOT_CONFIGURED_CODE_MSG)

    try:
        await run_blocking(verification_service.check_form_token, body.form_token or "")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    email = body.email.strip().lower()
    registered = auth_service.get_user_profile(email) is not None
    if body.purpose == "register" and registered:
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录")
    if body.purpose in ("login", "reset") and not registered:
        raise HTTPException(status_code=404, detail="该邮箱尚未注册，请先注册")
    # send_email / bind_email：受信邮箱验证，不做注册状态判定（防枚举中性处理）

    try:
        issued = await run_blocking(
            verification_service.issue_code,
            email,
            body.purpose,
            client_ip=_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    try:
        await run_blocking(
            email_service.send_verification_code,
            email,
            issued["code"],
            issued["expires_in"] // 60,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"验证码邮件发送失败：{exc}") from exc

    return {
        "message": "验证码已发送，请查收邮箱",
        "expires_in": issued["expires_in"],
        "resend_after": issued["resend_after"],
    }


@router.post("/register", response_class=UTF8JSONResponse)
async def register(body: RegisterRequest):
    # AUTH_REQUIRED 时默认禁止开放注册；需 ALLOW_SELF_REGISTER=true 或管理员预置账号
    if auth_service.AUTH_REQUIRED and not auth_service.ALLOW_SELF_REGISTER:
        raise HTTPException(
            status_code=403,
            detail="当前环境已关闭自助注册，请联系管理员开通账号",
        )
    # 验证码：开关开启时必须提供；未开启时若提供了也要校验（避免前端误以为过了）
    if verification_service.REQUIRE_EMAIL_VERIFICATION and not body.code:
        raise HTTPException(status_code=400, detail="请先获取邮箱验证码")
    if body.code:
        try:
            await run_blocking(
                verification_service.consume_code, body.email, "register", body.code
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        await run_blocking(auth_service.register_user, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # 注册邮箱即受信（验证码已证明所有权），供邮件交付直达
    email = body.email.strip().lower()
    await run_blocking(trusted_email_service.add_trusted_email, email, email, "register")
    return {"message": "注册成功，请登录"}



@router.post("/verify-reset-code", response_class=UTF8JSONResponse)
async def verify_reset_code(body: VerifyResetCodeRequest):
    """校验重置用的邮箱验证码；通过则签发一次性 reset_token。

    必须走这一步：/reset-password 只认 reset_token 不认验证码本身，
    否则「知道邮箱」即可重置他人密码。
    """
    email = body.email.strip().lower()
    if not auth_service.get_user_profile(email):
        raise HTTPException(status_code=404, detail="该邮箱尚未注册，请先注册")
    try:
        await run_blocking(verification_service.consume_code, email, "reset", body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await run_blocking(verification_service.issue_reset_ticket, email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reset-password", response_class=UTF8JSONResponse)
async def reset_password(body: ResetPasswordRequest):
    """凭一次性 reset_token 重置密码；成功后该账号既有 JWT 全部失效。"""
    try:
        email = await run_blocking(verification_service.consume_reset_ticket, body.reset_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        await run_blocking(auth_service.update_password, email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "密码已重置，请使用新密码登录"}


@router.post("/demo-login", response_class=UTF8JSONResponse)
async def demo_login():
    """一键演示登录：仅 DEMO_LOGIN_ENABLED=true 时可用，口令不离开服务端。"""
    if not auth_service.DEMO_LOGIN_ENABLED:
        raise HTTPException(status_code=403, detail="演示登录未开启")
    out = await run_blocking(auth_service.issue_demo_login_token)
    if not out:
        raise HTTPException(status_code=503, detail="演示账号未就绪，请检查 DEMO_USER_* 配置")
    return out
