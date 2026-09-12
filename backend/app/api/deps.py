"""认证依赖 — 读可选、写/订阅/角色强制鉴权（deny-by-default）。"""
from collections.abc import Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.services import auth_service
from app.services.sync_runner import run_blocking

security = HTTPBearer(auto_error=False)


async def _payload_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
    *,
    required: bool,
) -> dict | None:
    if credentials is None:
        if required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="需要登录才能访问此接口",
            )
        return None
    # verify_token_checked 在校验签名之外，还会（仅当 token 携带 pwd_ver 声明时）
    # 查库比对密码版本 —— 改密后旧 token 立即失效。查库是阻塞 IO，故走线程池。
    payload = await run_blocking(auth_service.verify_token_checked, credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录凭证无效或已过期",
        )
    return payload


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    """AUTH_REQUIRED=true 时强制登录；false 时尽量解析 token（供归属校验）。

    仅用于只读/演示端点。写操作、订阅与角色守卫请用 get_current_user /
    require_plan / require_roles（始终强制鉴权）。
    """
    if auth_service.AUTH_REQUIRED:
        return await _payload_from_credentials(credentials, required=True)
    if credentials is None:
        return None
    return await _payload_from_credentials(credentials, required=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """始终要求有效 JWT（注册门禁、管理员操作、写端点等）。"""
    user = await _payload_from_credentials(credentials, required=True)
    assert user is not None
    return user


def require_roles(*roles: str) -> Callable:
    """基于 JWT role 的 RBAC — 始终要求登录（deny-by-default）。"""

    async def _dep(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> dict:
        user = await get_current_user(credentials)
        role = user.get("role") or "user"
        if role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return user

    return _dep


def require_plan(*plans: str) -> Callable:
    """订阅分层守卫 — 始终要求登录；admin 或命中 plan 才放行。"""

    async def _dep(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> dict:
        user = await get_current_user(credentials)
        role = user.get("role") or "user"
        plan = user.get("plan") or "free"
        if role == "admin" or plan in plans:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该功能为定制用户专享，请升级后使用",
        )

    return _dep
