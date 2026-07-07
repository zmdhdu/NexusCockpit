"""
Vehicle Adapter Factory — 车控适配器工厂

根据 .env 中的 VEHICLE_ADAPTER 配置选择车控后端:
  - mock: 模拟模式 (开发测试用，不发送真实指令)
  - http: HTTP REST 模式 (通过 HTTP 接口与车机通信)
  - mcp-stdio: MCP stdio 模式 (通过标准输入输出与 MCP 服务通信)
"""

from __future__ import annotations

import json
import shlex
from typing import Optional

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.vehicle.base import BaseVehicleAdapter
from nexus.vehicle.http import HttpVehicleBusAdapter
from nexus.vehicle.mock import MockVehicleBus

logger = get_logger(__name__)


def build_vehicle_adapter() -> BaseVehicleAdapter:
    """根据环境变量 VEHICLE_ADAPTER 选择车控适配器。

    Returns:
        BaseVehicleAdapter 实例 (Mock/HTTP/MCP 之一)
    """
    config = get_config().vehicle

    adapter_kind = (config.adapter or "mock").strip().lower()
    base_url = (config.api_base_url or "").strip()

    # HTTP / REST 模式
    if adapter_kind in {"http", "rest", "remote"} and base_url:
        logger.info(f"Using HttpVehicleBusAdapter: {base_url}")
        return HttpVehicleBusAdapter(
            base_url,
            protocol=config.api_protocol,
            endpoint=config.api_endpoint,
            timeout=config.api_timeout,
            auth_token=config.api_token,
        )

    # MCP stdio 模式
    if adapter_kind in {"mcp-stdio", "mcp_stdio", "stdio"} and config.mcp_command:
        from nexus.vehicle.mcp import MCPStdioVehicleAdapter
        command = _parse_command_line(config.mcp_command)
        if config.mcp_args:
            command.extend(_parse_args_list(config.mcp_args))
        env = None  # 使用默认环境
        logger.info(f"Using MCPStdioVehicleAdapter: {command}")
        return MCPStdioVehicleAdapter(
            command=command,
            cwd=config.mcp_workdir or None,
            env=env,
            tool_timeout=config.api_timeout,
            validate_tools=config.mcp_validate_tools,
        )

    # 默认: Mock 模式
    logger.info("Using MockVehicleBus")
    return MockVehicleBus()


def _parse_command_line(command_raw: str) -> list[str]:
    try:
        if command_raw.startswith("["):
            parsed = json.loads(command_raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
    except Exception:
        pass
    if " " in command_raw or "\t" in command_raw:
        return [part for part in shlex.split(command_raw, posix=False) if part]
    return [command_raw]


def _parse_args_list(args_raw: str) -> list[str]:
    try:
        if args_raw.startswith("["):
            parsed = json.loads(args_raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
    except Exception:
        pass
    return [part for part in shlex.split(args_raw, posix=False) if part]
