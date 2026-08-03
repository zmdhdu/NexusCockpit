# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""车控总线适配器配置。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.config._common import _ENV_FILE


class VehicleConfig(BaseSettings):
    """车控总线配置。

    控制车控指令的发送方式:
    - mock: 模拟模式 (开发测试用，不发送真实指令)
    - http: HTTP REST 模式 (通过 HTTP 接口发送到车机)
    - mcp: MCP stdio 模式 (通过标准输入输出与 MCP 服务通信)
    """

    # 适配器类型: mock / http / mcp
    adapter: str = Field(default="mock", validation_alias="VEHICLE_ADAPTER")
    # HTTP 模式的车机 API 地址
    api_base_url: str = Field(default="", validation_alias="VEHICLE_API_BASE_URL")
    # HTTP 模式的协议类型
    api_protocol: str = Field(default="rest", validation_alias="VEHICLE_API_PROTOCOL")
    # HTTP 模式的接口路径
    api_endpoint: str = Field(
        default="/vehicle/tools/invoke", validation_alias="VEHICLE_API_ENDPOINT"
    )
    # HTTP 调用超时时间 (秒)
    api_timeout: float = Field(default=5.0, validation_alias="VEHICLE_API_TIMEOUT")
    # HTTP 认证 Token
    api_token: str | None = Field(default=None, validation_alias="VEHICLE_API_TOKEN")
    # MCP 模式的启动命令 (如 "python vehicle_mcp_server.py")
    mcp_command: str = Field(default="", validation_alias="VEHICLE_MCP_COMMAND")
    # MCP 启动参数
    mcp_args: str = Field(default="", validation_alias="VEHICLE_MCP_ARGS")
    # MCP 工作目录
    mcp_workdir: str = Field(default="", validation_alias="VEHICLE_MCP_WORKDIR")
    # 是否验证 MCP 工具列表
    mcp_validate_tools: bool = Field(
        default=True, validation_alias="VEHICLE_MCP_VALIDATE_TOOLS"
    )

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")
