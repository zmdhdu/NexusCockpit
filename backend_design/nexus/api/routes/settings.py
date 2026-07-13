# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
设置中心 API 路由 — v2.1 座舱管理/用户管理/中间件配置/声纹

Demo 阶段由 Python 提供 CRUD API。
生产环境由 Go 网关直接操作 MySQL。
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Path, UploadFile, File, Form, Request

from nexus.config import get_config
from nexus.core.cockpit_manager import get_cockpit_manager
from nexus.core.db_manager import get_db_manager
from nexus.core.logger import get_logger
from nexus.core.voiceprint import get_voiceprint_service
from nexus.models.cockpit import (
    CockpitCreateRequest,
    CockpitListResponse,
    CockpitResponse,
    CockpitUpdateRequest,
    MiddlewareConfigUpdate,
    UserCreateRequest,
    UserResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


# ============================================================
# 座舱管理 CRUD
# ============================================================

@router.get("/cockpits", response_model=CockpitListResponse)
async def list_cockpits() -> CockpitListResponse:
    """列出所有座舱。"""
    manager = get_cockpit_manager()
    cockpits = manager.list_cockpits(include_inactive=True)
    active = [c for c in cockpits if c.is_active]
    return CockpitListResponse(
        total=len(cockpits),
        active=len(active),
        cockpits=[CockpitResponse(**c.to_dict()) for c in cockpits],
    )


@router.post("/cockpits", response_model=CockpitResponse)
async def register_cockpit(body: CockpitCreateRequest) -> CockpitResponse:
    """注册新座舱。"""
    manager = get_cockpit_manager()
    config = manager.register_cockpit(
        name=body.name,
        user_id=body.user_id,
        vehicle_adapter=body.vehicle_adapter,
        theme_color=body.theme_color,
    )
    return CockpitResponse(**config.to_dict())


@router.put("/cockpits/{cockpit_id}", response_model=CockpitResponse)
async def update_cockpit(
    cockpit_id: str = Path(...),
    body: CockpitUpdateRequest = ...,
) -> CockpitResponse:
    """更新座舱配置。"""
    manager = get_cockpit_manager()
    updates = body.model_dump(exclude_none=True)
    config = manager.update_cockpit(cockpit_id, updates)
    if not config:
        raise HTTPException(status_code=404, detail=f"Cockpit {cockpit_id} not found")
    return CockpitResponse(**config.to_dict())


@router.delete("/cockpits/{cockpit_id}")
async def delete_cockpit(cockpit_id: str = Path(...)) -> Dict[str, Any]:
    """注销座舱（软删除）。"""
    manager = get_cockpit_manager()
    success = manager.unregister_cockpit(cockpit_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Cockpit {cockpit_id} not found")
    return {"success": True, "message": f"Cockpit {cockpit_id} deactivated"}


# ============================================================
# 用户管理（持久化到 MySQL）
# ============================================================

@router.get("/users", response_model=List[UserResponse])
async def list_users(request: Request) -> List[UserResponse]:
    """列出所有用户。"""
    db = get_db_manager()
    if db.is_connected:
        users = await db.list_users()
    else:
        # 降级：MySQL 不可用时返回空列表
        users = []
    return [
        UserResponse(
            user_id=u["user_id"],
            username=u["username"],
            cockpit_id=u.get("cockpit_id") or "",
            role=u.get("role") or "cockpit_user",
            created_at=u.get("created_at") or "",
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse)
async def register_user(body: UserCreateRequest, request: Request) -> UserResponse:
    """注册新用户。"""
    db = get_db_manager()
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not available")

    # 检查是否已存在
    existing = await db.get_user(body.user_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"User {body.user_id} already exists")

    # 创建用户
    import hashlib
    password_hash = None
    if body.password:
        password_hash = hashlib.sha256(body.password.encode()).hexdigest()

    user = await db.create_user(
        user_id=body.user_id,
        username=body.username,
        cockpit_id=body.cockpit_id,
        role=body.role,
        password_hash=password_hash,
    )
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user")

    # 写入审计日志
    await db.insert_audit_log(
        cockpit_id=body.cockpit_id or "global",
        user_id=body.user_id,
        action="user_register",
        detail={"username": body.username, "role": body.role},
    )

    return UserResponse(**user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str = Path(...),
    request: Request = ...,
) -> Dict[str, Any]:
    """删除用户。"""
    db = get_db_manager()
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database not available")

    success = await db.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    # 写入审计日志
    await db.insert_audit_log(
        cockpit_id="global",
        user_id=user_id,
        action="user_delete",
    )

    return {"success": True, "message": f"User {user_id} deleted"}


# ============================================================
# 中间件配置
# ============================================================

@router.get("/middleware")
async def get_middleware_config() -> Dict[str, Any]:
    """获取中间件配置。"""
    config = get_config().cockpit
    redis_config = get_config().redis
    return {
        "isolation_mode": config.isolation_mode,
        "subagent_check_min": config.subagent_check_interval_min,
        "subagent_check_max": config.subagent_check_interval_max,
        "mainagent_confirm_enabled": config.mainagent_confirm_enabled,
        "cache_similarity_threshold": redis_config.cache_similarity_threshold,
        "rate_limit_qps": 100,
    }


@router.put("/middleware")
async def update_middleware_config(body: MiddlewareConfigUpdate) -> Dict[str, Any]:
    """更新中间件配置（热更新）。"""
    updated_fields = body.model_dump(exclude_none=True)
    if not updated_fields:
        return {"success": False, "message": "No fields to update"}

    # 将配置变更写入 Redis（热更新通道）
    try:
        import redis.asyncio as aioredis
        import json
        from nexus.config import get_config
        redis_config = get_config().redis
        client = aioredis.Redis(
            host=redis_config.host, port=redis_config.port,
            password=redis_config.password, db=redis_config.db,
            decode_responses=True,
        )
        # 写入配置缓存
        config_key = "middleware:config"
        await client.hset(config_key, mapping={
            k: json.dumps(v, ensure_ascii=False) for k, v in updated_fields.items()
        })
        # 发布配置变更通知
        await client.publish("config:update", json.dumps(updated_fields, ensure_ascii=False))
        await client.close()

        logger.info(f"Middleware config updated: {list(updated_fields.keys())}")
        return {
            "success": True,
            "updated_fields": updated_fields,
            "message": "Configuration updated and hot reload triggered via Redis Pub/Sub",
        }
    except Exception as e:
        logger.error(f"Failed to hot reload middleware config: {e}")
        return {
            "success": False,
            "updated_fields": updated_fields,
            "message": f"Hot reload failed: {e}",
        }


# ============================================================
# 声纹管理
# ============================================================

@router.get("/voiceprint/status")
async def get_voiceprint_status(cockpit_id: str = "") -> Dict[str, Any]:
    """获取声纹注册状态。"""
    service = get_voiceprint_service()
    if cockpit_id:
        return service.get_status(cockpit_id)
    # 返回所有座舱的声纹状态
    manager = get_cockpit_manager()
    result = {}
    for c in manager.list_cockpits():
        result[c.cockpit_id] = service.get_status(c.cockpit_id)
    return {"cockpits": result}


@router.post("/voiceprint/enroll")
async def enroll_voiceprint(
    cockpit_id: str = Form(...),
    user_id: str = Form(...),
    audio: UploadFile = File(...),
) -> Dict[str, Any]:
    """声纹注册。"""
    service = get_voiceprint_service()
    audio_data = await audio.read()
    audio_format = audio.filename.split(".")[-1] if audio.filename else "wav"
    return await service.enroll(cockpit_id, user_id, audio_data, audio_format)


@router.post("/voiceprint/verify")
async def verify_voiceprint(
    cockpit_id: str = Form(...),
    audio: UploadFile = File(...),
) -> Dict[str, Any]:
    """声纹验证 — 验证成功后自动签发 JWT Token（N9）。

    验证流程:
    1. 提取音频声纹特征，与该座舱下已注册用户比对
    2. 验证成功 → 自动签发包含 cockpit_id + user_id + role 的 JWT Token
    3. 前端可直接使用该 Token 进行后续操作（无需再调用 /auth/token）
    """
    service = get_voiceprint_service()
    audio_data = await audio.read()
    audio_format = audio.filename.split(".")[-1] if audio.filename else "wav"
    result = await service.verify(cockpit_id, audio_data, audio_format)

    # 声纹验证成功 → 自动签发 JWT Token
    if result.get("verified") and result.get("user_id"):
        user_id = result["user_id"]
        try:
            from nexus.core.auth import create_access_token
            from datetime import timedelta
            from nexus.config import get_config

            jwt_config = get_config().jwt

            # 查询用户角色（从 MySQL，降级为默认角色）
            role = "cockpit_user"
            db = get_db_manager()
            if db.is_connected:
                try:
                    user = await db.get_user(user_id)
                    if user and user.get("role"):
                        role = user["role"]
                except Exception:
                    pass

            # 签发包含座舱和角色信息的 JWT Token
            token = create_access_token(
                user_id=user_id,
                expires_delta=timedelta(minutes=jwt_config.expire_minutes),
                extra_claims={
                    "cockpit_id": cockpit_id,
                    "role": role,
                    "auth_method": "voiceprint",
                },
            )

            result["access_token"] = token
            result["token_type"] = "Bearer"
            result["expires_in"] = jwt_config.expire_minutes * 60
            result["auth_method"] = "voiceprint"
            logger.info(
                f"Voiceprint verified, JWT auto-issued: "
                f"cockpit={cockpit_id}, user={user_id}, role={role}"
            )
        except Exception as e:
            logger.error(f"Failed to auto-issue JWT after voiceprint verify: {e}")
            result["jwt_error"] = str(e)

    return result


@router.delete("/voiceprint/{user_id}")
async def delete_voiceprint(
    user_id: str = Path(...),
    cockpit_id: str = "",
) -> Dict[str, Any]:
    """删除声纹。"""
    service = get_voiceprint_service()
    if not cockpit_id:
        # 删除所有座舱下该用户的声纹
        manager = get_cockpit_manager()
        for c in manager.list_cockpits():
            service.delete_voiceprint(c.cockpit_id, user_id)
        return {"success": True, "message": f"Deleted voiceprint for user {user_id} in all cockpits"}

    success = service.delete_voiceprint(cockpit_id, user_id)
    return {"success": success, "cockpit_id": cockpit_id, "user_id": user_id}
