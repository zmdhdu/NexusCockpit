"""
Vehicle Routes — 车控命令 REST 接口

提供两个端点:
  POST /vehicle/command — 直接执行车控命令 (不经过 Agent 工作流)
  GET  /vehicle/status  — 获取车辆当前状态

v2.1 多座舱隔离:
  每个座舱拥有独立的车控适配器实例，
  从请求头 X-Cockpit-Id 或 tenant_context 获取座舱 ID，
  确保 cockpit-01 的空调温度不影响 cockpit-02。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from nexus.core.auth import get_current_user
from nexus.core.logger import get_logger
from nexus.core.tenant_context import get_cockpit_id
from nexus.models.schemas import VehicleCommandRequest, VehicleCommandResponse
from nexus.observability.metrics import SKILL_EXECUTIONS
from nexus.vehicle.factory import get_cockpit_vehicle_adapter

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicle", tags=["vehicle"])


def _get_adapter(request: Request):
    """获取当前请求对应座舱的车控适配器。

    优先从 tenant_context 获取 cockpit_id（由中间件从 X-Cockpit-Id 头设置），
    如果没有则回退到全局单例适配器。
    """
    cockpit_id = get_cockpit_id()
    if cockpit_id:
        return get_cockpit_vehicle_adapter(cockpit_id)
    # 回退: 使用全局单例
    return request.app.state.vehicle_adapter


@router.post("/command", response_model=VehicleCommandResponse)
async def vehicle_command(
    request: Request,
    body: VehicleCommandRequest,
    user_id: str = Depends(get_current_user),
):
    """直接执行车控命令 (绕过 Agent 工作流)。

    需要 JWT 认证。适用于前端车控面板的按钮直接调用。
    每个座舱拥有独立的车控状态（v2.1 隔离）。

    Args:
        body: 包含 command 和 arguments 的请求体
        user_id: 从 JWT Token 中解析的当前用户 ID

    Returns:
        VehicleCommandResponse 包含执行结果
    """
    adapter = _get_adapter(request)

    result = adapter.invoke_command(body.command, body.arguments)
    SKILL_EXECUTIONS.labels(skill_name=body.command, status="ok" if result.success else "error").inc()

    return VehicleCommandResponse(
        success=result.success,
        message=result.message,
        data=result.data,
        error=result.error,
    )


@router.get("/status")
async def vehicle_status(request: Request, user_id: str = Depends(get_current_user)):
    """获取车辆当前状态 (空调、车窗、座椅、媒体、导航、车况)。

    需要JWT认证。
    每个座舱返回各自独立的车控状态（v2.1 隔离）。

    Returns:
        包含车辆各子系统状态的字典
    """
    adapter = _get_adapter(request)
    result = adapter.vehicle_status()
    # 返回扁平结构，前端 VehicleStatus 类型直接匹配
    return result.data


class LocationUpdate(BaseModel):
    """浏览器 GPS 定位更新请求。"""
    latitude: float
    longitude: float


@router.post("/location")
async def update_location(
    request: Request,
    body: LocationUpdate,
    user_id: str = Depends(get_current_user),
):
    """使用浏览器 GPS 坐标更新当前位置。

    前端通过 navigator.geolocation.getCurrentPosition() 获取坐标后，
    调用此接口将坐标发送给后端进行逆地理编码，获取人类可读的地址。
    """
    adapter = _get_adapter(request)

    # v2.2.3: 仅存储 GPS 坐标到 adapter，不触发逆地理编码
    # 逆地理编码在用户查询位置/周边时按需调用（通过 NavExpert 或 POI 搜索技能）
    if hasattr(adapter, "navigation"):
        adapter.navigation["latitude"] = body.latitude
        adapter.navigation["longitude"] = body.longitude
        # 清除旧的缓存地址，下次查询时会重新逆地理编码
        adapter.navigation["current_location"] = ""
        return {
            "success": True,
            "location": "",
            "latitude": body.latitude,
            "longitude": body.longitude,
            "message": "坐标已更新，地址将在查询时获取",
        }

    return {"success": False, "message": "Vehicle adapter does not support location update"}
