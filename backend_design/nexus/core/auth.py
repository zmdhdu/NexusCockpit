# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
JWT Authentication — 认证模块

提供 JWT Token 的签发与验证，保护车控指令和管理接口的安全。
所有需要认证的路由通过 Depends(get_current_user) 注入当前用户。

认证流程:
  1. 客户端调用 POST /auth/token 获取 JWT Token
  2. 后续请求在 Authorization 头中携带 "Bearer <token>"
  3. get_current_user 依赖验证 Token 并返回用户信息
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nexus.config import get_config
from nexus.core.exceptions import AuthError
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# Bearer Token 提取器 — 自动从 Authorization 头解析
security = HTTPBearer(auto_error=False)


def create_access_token(
    user_id: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict | None = None,
) -> str:
    """签发 JWT Access Token。

    Args:
        user_id: 用户唯一标识
        expires_delta: 自定义过期时长 (默认使用配置中的 expire_minutes)
        extra_claims: 额外的 JWT claims (如 role, permissions)

    Returns:
        编码后的 JWT 字符串
    """
    config = get_config().jwt
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=config.expire_minutes))
    payload = {
        "sub": user_id,           # subject: 用户 ID
        "exp": expire,            # expiration: 过期时间
        "iat": now,               # issued at: 签发时间
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, config.secret_key, algorithm=config.algorithm)


def decode_token(token: str) -> dict:
    """解码并验证 JWT Token。

    Args:
        token: JWT 字符串

    Returns:
        解码后的 payload 字典

    Raises:
        AuthError: Token 无效或过期
    """
    config = get_config().jwt
    try:
        return jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
    except jwt.ExpiredSignatureError:
        raise AuthError("Token 已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise AuthError("Token 无效")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """FastAPI 依赖: 验证 JWT Token 并返回用户 ID。

    用法:
        @router.post("/command")
        async def vehicle_command(user: str = Depends(get_current_user)):
            ...

    Raises:
        HTTPException 401: 未提供 Token 或 Token 无效
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据，请在 Authorization 头中携带 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 中缺少用户标识",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str | None:
    """FastAPI 依赖: 可选认证，Token 有效时返回 user_id，无效或缺失时返回 None。

    适用于聊天等不强制认证但可以受益于认证的场景。
    """
    if credentials is None:
        return None

    try:
        payload = decode_token(credentials.credentials)
        return payload.get("sub")
    except AuthError:
        return None
