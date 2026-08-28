"""认证依赖 — AUTH_REQUIRED=false 时演示放行；true 时全端点强制 JWT。"""
from collections.abc import Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.services import auth_service

security = HTTPBearer(auto_error=False)


def _payload_from_credentials(
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
    payload = auth_service.verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录凭证无效或已过期",
        )
    return payload


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    """AUTH_REQUIRED=true 时强制登录；false 时尽量解析 token（供归属校验）。"""
    if auth_service.AUTH_REQUIRED:
        return _payload_from_credentials(credentials, required=True)
    if credentials is None:
        return None
    return _payload_from_credentials(credentials, required=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """始终要求有效 JWT（注册门禁、管理员操作等）。"""
    user = _payload_from_credentials(credentials, required=True)
    assert user is not None
    return user


def require_roles(*roles: str) -> Callable:
    """基于 JWT role 的基础 RBAC。

    演示态（AUTH_REQUIRED=false）未登录时放行，与 get_current_user_optional 一致；
    已登录（或 AUTH_REQUIRED=true）时校验 role。
    """

    async def _dep(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> dict | None:
        user = await get_current_user_optional(credentials)
        if user is None:
            return None
        role = user.get("role") or "user"
        if role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return user

    return _dep
