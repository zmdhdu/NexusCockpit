"""
Vehicle Routes — 车控命令 REST 接口

提供两个端点:
  POST /vehicle/command — 直接执行车控命令 (不经过 Agent 工作流)
  GET  /vehicle/status  — 获取车辆当前状态
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from nexus.core.logger import get_logger
from nexus.models.schemas import VehicleCommandRequest, VehicleCommandResponse
from nexus.observability.metrics import SKILL_EXECUTIONS

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicle", tags=["vehicle"])


@router.post("/command", response_model=VehicleCommandResponse)
async def vehicle_command(request: Request, body: VehicleCommandRequest):
    """直接执行车控命令 (绕过 Agent 工作流)。

    适用于前端车控面板的按钮直接调用。

    Args:
        body: 包含 command 和 arguments 的请求体

    Returns:
        VehicleCommandResponse 包含执行结果
    """
    app = request.app
    adapter = app.state.vehicle_adapter

    result = adapter.invoke_command(body.command, body.arguments)
    SKILL_EXECUTIONS.labels(skill_name=body.command, status="ok" if result.success else "error").inc()

    return VehicleCommandResponse(
        success=result.success,
        message=result.message,
        data=result.data,
        error=result.error,
    )


@router.get("/status")
async def vehicle_status(request: Request):
    """获取车辆当前状态 (空调、车窗、媒体等)。

    Returns:
        包含车辆各子系统状态的字典
    """
    app = request.app
    adapter = app.state.vehicle_adapter
    result = adapter.vehicle_status()
    return {
        "success": result.success,
        "message": result.message,
        "data": result.data,
    }
