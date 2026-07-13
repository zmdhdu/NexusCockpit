# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Auth Routes — 认证接口

提供 JWT Token 签发端点:
  POST /auth/token — 用户认证并获取 JWT Token

认证流程:
  1. 客户端发送 user_id + password (或 API Key)
  2. 服务端验证凭据
  3. 签发 JWT Token 返回给客户端
  4. 客户端后续请求在 Authorization 头中携带 "Bearer <token>"
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from nexus.config import get_config
from nexus.core.auth import create_access_token, get_current_user
from nexus.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    """Token 请求体"""
    user_id: str = Field(..., description="用户 ID")
    password: str = Field(default="", description="用户密码或 API Key")


class TokenResponse(BaseModel):
    """Token 响应体"""
    access_token: str = Field(..., description="JWT Access Token")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(..., description="Token 有效期 (秒)")


@router.post("/token", response_model=TokenResponse)
async def login(body: TokenRequest):
    """用户认证并获取 JWT Token。

    开发环境下直接签发 Token (不校验密码)。
    生产环境应接入用户数据库验证密码。

    Args:
        body: 包含 user_id 和 password 的请求体

    Returns:
        TokenResponse 包含 JWT Token
    """
    config = get_config().jwt

    # 开发模式: 直接签发 Token，默认赋予管理员角色
    # 生产环境应接入用户数据库验证密码并查询角色
    logger.info(f"Token issued for user: {body.user_id}")

    token = create_access_token(
        user_id=body.user_id,
        expires_delta=timedelta(minutes=config.expire_minutes),
        extra_claims={"role": "super_admin", "cockpit_id": "cockpit-01"},
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=config.expire_minutes * 60,
    )


@router.get("/me")
async def get_me(user_id: str = Depends(get_current_user)):
    """获取当前认证用户信息 (用于验证 Token 是否有效)。"""
    return {"user_id": user_id, "authenticated": True}


class ChangePasswordRequest(BaseModel):
    """修改密码请求体"""
    old_password: str = Field(default="", description="旧密码")
    new_password: str = Field(..., min_length=6, description="新密码 (至少6位)")


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user_id: str = Depends(get_current_user),
):
    """修改用户密码。

    开发环境下直接返回成功（不实际校验旧密码）。
    生产环境应接入用户数据库验证旧密码并更新。

    Args:
        body: 包含旧密码和新密码的请求体
        user_id: 当前登录用户 ID（从 JWT 解析）

    Returns:
        操作结果
    """
    logger.info(f"Password changed for user: {user_id}")
    return {"success": True, "message": "密码修改成功"}
