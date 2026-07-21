# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Vehicle Adapter Factory — 车控适配器工厂

根据 .env 中的 VEHICLE_ADAPTER 配置选择车控后端:
  - mock: 模拟模式 (开发测试用，不发送真实指令)
  - http: HTTP REST 模式 (通过 HTTP 接口与车机通信)
  - mcp-stdio: MCP stdio 模式 (通过标准输入输出与 MCP 服务通信)

多座舱隔离:
  Mock 模式下，每个座舱拥有独立的 MockVehicleBus 实例，
  实现空调温度、车窗等状态的物理隔离。
"""

from __future__ import annotations

import json
import shlex

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.vehicle.base import BaseVehicleAdapter
from nexus.vehicle.http import HttpVehicleBusAdapter
from nexus.vehicle.mock import MockVehicleBus

logger = get_logger(__name__)

# 模块级单例 — 避免每次调用都创建新实例（SubAgent 巡检、技能实例化等场景）
_singleton_adapter: BaseVehicleAdapter | None = None

# 每座舱独立的车控适配器实例（MockVehicleBus 状态隔离）
_cockpit_adapters: dict[str, BaseVehicleAdapter] = {}


def build_vehicle_adapter() -> BaseVehicleAdapter:
    """根据环境变量 VEHICLE_ADAPTER 选择车控适配器（单例）。

    首次调用时创建实例，后续调用直接返回同一实例，
    避免 SubAgent 巡检等周期性任务反复初始化。

    Returns:
        BaseVehicleAdapter 实例 (Mock/HTTP/MCP 之一)
    """
    global _singleton_adapter
    if _singleton_adapter is not None:
        return _singleton_adapter

    _singleton_adapter = _create_adapter()
    return _singleton_adapter


def get_cockpit_vehicle_adapter(cockpit_id: str) -> BaseVehicleAdapter:
    """获取指定座舱的车控适配器实例（多座舱隔离）。

    每个座舱拥有独立的 MockVehicleBus 实例，
    这样座舱 A 的空调温度不会影响座舱 B。

    对于 HTTP/MCP 模式（无状态），复用单例。

    Args:
        cockpit_id: 座舱 ID，如 "cockpit-01"

    Returns:
        该座舱专属的车控适配器实例
    """
    global _cockpit_adapters

    if cockpit_id not in _cockpit_adapters:
        config = get_config().vehicle
        adapter_kind = (config.adapter or "mock").strip().lower()

        if adapter_kind == "mock":
            # Mock 模式: 每座舱独立实例（状态隔离）
            logger.info(f"Creating MockVehicleBus for cockpit: {cockpit_id}")
            _cockpit_adapters[cockpit_id] = MockVehicleBus()
        else:
            # HTTP/MCP 模式: 无状态，复用单例
            _cockpit_adapters[cockpit_id] = build_vehicle_adapter()

    return _cockpit_adapters[cockpit_id]


def _create_adapter() -> BaseVehicleAdapter:
    """实际创建车控适配器实例（内部函数）。"""
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
    logger.info("Using MockVehicleBus (singleton)")
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
