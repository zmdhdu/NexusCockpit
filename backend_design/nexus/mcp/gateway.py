# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
MCP Gateway — MCP (Model Context Protocol) 网关
统一管理外部工具调用，支持车控工具的 MCP 协议暴露
"""

from __future__ import annotations

from typing import Any, Dict

from nexus.core.logger import get_logger
from nexus.vehicle.base import VehicleCommandResult

logger = get_logger(__name__)


class MCPGateway:
    """
    MCP 网关 — 统一工具调用入口
    封装 vehicle adapter，提供统一的 invoke 接口
    """

    def __init__(self, adapter=None):
        from nexus.vehicle.factory import build_vehicle_adapter
        self.adapter = adapter or build_vehicle_adapter()

    def invoke(self, tool_name: str, arguments: Dict[str, Any]) -> VehicleCommandResult:
        """调用工具"""
        result = self.adapter.invoke_command(tool_name, arguments)
        if not result.success:
            logger.warning(
                f"MCP invoke failed: tool={tool_name}, error={result.error}"
            )
        return result

    def list_tools(self) -> list[dict]:
        """列出可用工具"""
        return [
            {
                "name": "vehicle_climate",
                "description": "调整空调温度、风量和模式",
            },
            {
                "name": "vehicle_window",
                "description": "控制车窗或天窗",
            },
            {
                "name": "vehicle_seat",
                "description": "控制座椅加热、通风、按摩",
            },
            {
                "name": "vehicle_navigation",
                "description": "发起导航",
            },
            {
                "name": "vehicle_media",
                "description": "控制媒体播放",
            },
            {
                "name": "vehicle_status",
                "description": "查询车辆状态",
            },
        ]
