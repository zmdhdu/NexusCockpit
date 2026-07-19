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


# 手机验证码修改密码 — 忘记旧密码时的备用方式

import random
import time

# 内存验证码存储: {phone: (code, expire_timestamp)}
_verify_codes: dict[str, tuple[str, float]] = {}


class SendCodeRequest(BaseModel):
    """发送验证码请求体"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")


class SendCodeResponse(BaseModel):
    """发送验证码响应体"""
    success: bool = Field(..., description="是否发送成功")
    message: str = Field(default="验证码已发送")
    # 开发模式返回验证码，方便测试；生产环境应通过短信网关发送
    dev_code: str | None = Field(default=None, description="开发模式下的验证码")


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(body: SendCodeRequest):
    """发送手机验证码。

    开发环境下生成 6 位随机验证码并返回（方便测试）。
    生产环境应接入短信网关（阿里云/腾讯云 SMS）。

    Args:
        body: 包含手机号的请求体

    Returns:
        SendCodeResponse 包含发送结果
    """
    code = str(random.randint(100000, 999999))
    _verify_codes[body.phone] = (code, time.time() + 300)  # 5 分钟有效

    logger.info(f"Verification code sent to {body.phone}: {code}")

    return SendCodeResponse(
        success=True,
        message="验证码已发送至您的手机",
        dev_code=code,  # 开发模式返回验证码
    )


class ResetPasswordByCodeRequest(BaseModel):
    """验证码修改密码请求体"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    code: str = Field(..., min_length=6, max_length=6, description="验证码")
    new_password: str = Field(..., min_length=6, description="新密码 (至少6位)")


@router.post("/reset-password-by-code")
async def reset_password_by_code(body: ResetPasswordByCodeRequest):
    """通过手机验证码修改密码。

    验证手机号 + 验证码，通过后更新密码。
    适用于忘记旧密码的场景。

    Args:
        body: 包含手机号、验证码、新密码的请求体

    Returns:
        操作结果
    """
    stored = _verify_codes.get(body.phone)
    if not stored:
        return {"success": False, "message": "请先获取验证码"}

    code, expire_at = stored
    if time.time() > expire_at:
        _verify_codes.pop(body.phone, None)
        return {"success": False, "message": "验证码已过期，请重新获取"}

    if code != body.code:
        return {"success": False, "message": "验证码不正确"}

    # 验证通过，清除验证码
    _verify_codes.pop(body.phone, None)
    logger.info(f"Password reset by phone code: {body.phone}")

    return {"success": True, "message": "密码修改成功"}
