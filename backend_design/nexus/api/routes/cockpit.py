# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
座舱 API 路由 — v2.1 多座舱对话/车控/状态接口

所有路由以 /cockpit/{cockpit_id} 为前缀，
支持按座舱隔离的对话、车控、状态查询。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field

from nexus.core.cockpit_manager import get_cockpit_manager
from nexus.core.logger import get_logger
from nexus.core.tenant_context import CockpitContext, set_cockpit_id, set_user_id
from nexus.models.cockpit import (
    CockpitResponse,
    CockpitStatusResponse,
)
from nexus.observability.cockpit_metrics import get_cockpit_metrics

logger = get_logger(__name__)

router = APIRouter(prefix="/cockpit", tags=["cockpit"])


# ============================================================
# 请求模型
# ============================================================

class ChatRequestBody(BaseModel):
    """座舱对话请求。"""
    text: str = Field(..., description="用户输入文本")
    user_id: str = Field(default="default", description="用户 ID")
    stream: bool = Field(default=False, description="是否流式返回")


class VehicleCommandBody(BaseModel):
    """车控指令请求。"""
    command: str = Field(..., description="命令名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="命令参数")
    user_id: str = Field(default="default", description="用户 ID")


# ============================================================
# 路由
# ============================================================

@router.get("/{cockpit_id}/status", response_model=CockpitStatusResponse)
async def get_cockpit_status(
    cockpit_id: str = Path(..., description="座舱 ID"),
) -> CockpitStatusResponse:
    """获取座舱状态（含车辆状态和指标）。"""
    manager = get_cockpit_manager()
    config = manager.get_cockpit(cockpit_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Cockpit {cockpit_id} not found")

    # 获取实时指标
    metrics = await get_cockpit_metrics().get_cockpit_stats(cockpit_id)

    return CockpitStatusResponse(
        cockpit_id=config.cockpit_id,
        name=config.name,
        is_active=config.is_active,
        vehicle_status=None,  # TODO: 从 vehicle adapter 获取
        metrics=metrics,
    )


@router.post("/{cockpit_id}/chat")
async def cockpit_chat(
    request: Request,
    cockpit_id: str = Path(..., description="座舱 ID"),
    body: ChatRequestBody = ...,
) -> Dict[str, Any]:
    """座舱对话（转发到 Agent 工作流）。

    设置 TenantContext 后调用 SupervisorGraph。
    """
    manager = get_cockpit_manager()
    config = manager.get_cockpit(cockpit_id)
    if not config or not config.is_active:
        raise HTTPException(status_code=404, detail=f"Cockpit {cockpit_id} not found or inactive")

    agent_graph = getattr(request.app.state, "agent_graph", None)
    if not agent_graph:
        raise HTTPException(status_code=503, detail="Agent graph not initialized")

    # 设置多租户上下文
    with CockpitContext(cockpit_id, body.user_id):
        from nexus.models.state import create_initial_state

        state = create_initial_state(
            user_input=body.text,
            user_id=body.user_id,
            session_id=f"{cockpit_id}:{body.user_id}",
        )
        state["cockpit_id"] = cockpit_id

        # 检查缓存
        cache = getattr(request.app.state, "semantic_cache", None)
        if cache and cache._enabled:
            try:
                cached = await cache.get(body.text, body.user_id)
                if cached:
                    await get_cockpit_metrics().record_chat(cockpit_id, 0, True)
                    return {
                        "response": cached.get("response", ""),
                        "cockpit_id": cockpit_id,
                        "cache_hit": True,
                        "metadata": cached.get("metadata", {}),
                    }
            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}")

        # 执行 Agent 工作流
        import time
        t0 = time.perf_counter()
        result = await agent_graph.invoke(state)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        # 记录指标
        await get_cockpit_metrics().record_chat(cockpit_id, latency_ms, False)

        # 写入缓存（非副作用响应）
        final_response = result.get("final_response", "")
        if cache and cache._enabled and not result.get("has_side_effect"):
            try:
                await cache.set(body.text, final_response, body.user_id)
            except Exception as e:
                logger.warning(f"Cache write failed: {e}")

        return {
            "response": final_response,
            "cockpit_id": cockpit_id,
            "cache_hit": False,
            "latency_ms": latency_ms,
            "metadata": result.get("metadata", {}),
        }


@router.post("/{cockpit_id}/chat/stream")
async def cockpit_chat_stream(
    request: Request,
    cockpit_id: str = Path(..., description="座舱 ID"),
    body: ChatRequestBody = ...,
):
    """座舱流式对话。"""
    from fastapi.responses import StreamingResponse

    manager = get_cockpit_manager()
    config = manager.get_cockpit(cockpit_id)
    if not config or not config.is_active:
        raise HTTPException(status_code=404, detail=f"Cockpit {cockpit_id} not found or inactive")

    agent_graph = getattr(request.app.state, "agent_graph", None)
    if not agent_graph:
        raise HTTPException(status_code=503, detail="Agent graph not initialized")

    async def stream_generator():
        # 使用 try/finally 确保 CockpitContext 在生成器被提前关闭时也能正确重置
        # （客户端断开连接时 async generator 会被 aclose()，触发 GeneratorExit）
        ctx = CockpitContext(cockpit_id, body.user_id)
        ctx.__enter__()
        try:
            from nexus.models.state import create_initial_state

            state = create_initial_state(
                user_input=body.text,
                user_id=body.user_id,
                session_id=f"{cockpit_id}:{body.user_id}",
            )
            state["cockpit_id"] = cockpit_id

            async for chunk in agent_graph.stream(state):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except GeneratorExit:
            # 客户端断开连接，正常退出
            raise
        except Exception as e:
            logger.error(f"Stream generator error for {cockpit_id}: {e}")
            yield f"data: {{\"error\": \"{e}\"}}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            ctx.__exit__(None, None, None)

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
    )


@router.post("/{cockpit_id}/vehicle/cmd")
async def cockpit_vehicle_cmd(
    request: Request,
    cockpit_id: str = Path(..., description="座舱 ID"),
    body: VehicleCommandBody = ...,
) -> Dict[str, Any]:
    """座舱车控指令执行。"""
    manager = get_cockpit_manager()
    config = manager.get_cockpit(cockpit_id)
    if not config or not config.is_active:
        raise HTTPException(status_code=404, detail=f"Cockpit {cockpit_id} not found or inactive")

    vehicle_adapter = getattr(request.app.state, "vehicle_adapter", None)
    if not vehicle_adapter:
        raise HTTPException(status_code=503, detail="Vehicle adapter not initialized")

    with CockpitContext(cockpit_id, body.user_id):
        try:
            result = await vehicle_adapter.execute(body.command, body.arguments)
            await get_cockpit_metrics().record_vehicle_cmd(cockpit_id, True)
            return {
                "success": True,
                "cockpit_id": cockpit_id,
                "result": result,
            }
        except Exception as e:
            await get_cockpit_metrics().record_vehicle_cmd(cockpit_id, False)
            logger.error(f"Vehicle command failed: {e}")
            return {
                "success": False,
                "cockpit_id": cockpit_id,
                "error": str(e),
            }


@router.get("/{cockpit_id}/vehicle/status")
async def cockpit_vehicle_status(
    request: Request,
    cockpit_id: str = Path(..., description="座舱 ID"),
) -> Dict[str, Any]:
    """获取座舱的车辆状态。"""
    manager = get_cockpit_manager()
    config = manager.get_cockpit(cockpit_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Cockpit {cockpit_id} not found")

    vehicle_adapter = getattr(request.app.state, "vehicle_adapter", None)
    if not vehicle_adapter:
        raise HTTPException(status_code=503, detail="Vehicle adapter not initialized")

    with CockpitContext(cockpit_id):
        try:
            status = vehicle_adapter.get_status()
            return {
                "cockpit_id": cockpit_id,
                "status": status,
            }
        except Exception as e:
            return {
                "cockpit_id": cockpit_id,
                "error": str(e),
            }
