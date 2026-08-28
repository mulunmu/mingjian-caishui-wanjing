from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app.responses import UTF8JSONResponse
from app.services import auth_service
from app.services.sync_runner import run_blocking

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_class=UTF8JSONResponse)
async def login(body: LoginRequest):
    user = await run_blocking(auth_service.authenticate_user, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = auth_service.create_access_token(user["email"], user["role"], user["plan"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "plan": user["plan"],
    }


@router.post("/register", response_class=UTF8JSONResponse)
async def register(body: RegisterRequest):
    # AUTH_REQUIRED 时默认禁止开放注册；需 ALLOW_SELF_REGISTER=true 或管理员预置账号
    if auth_service.AUTH_REQUIRED and not auth_service.ALLOW_SELF_REGISTER:
        raise HTTPException(
            status_code=403,
            detail="当前环境已关闭自助注册，请联系管理员开通账号",
        )
    try:
        await run_blocking(auth_service.register_user, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "注册成功，请登录"}


@router.post("/demo-login", response_class=UTF8JSONResponse)
async def demo_login():
    """一键演示登录：仅 DEMO_LOGIN_ENABLED=true 时可用，口令不离开服务端。"""
    if not auth_service.DEMO_LOGIN_ENABLED:
        raise HTTPException(status_code=403, detail="演示登录未开启")
    out = await run_blocking(auth_service.issue_demo_login_token)
    if not out:
        raise HTTPException(status_code=503, detail="演示账号未就绪，请检查 DEMO_USER_* 配置")
    return out
