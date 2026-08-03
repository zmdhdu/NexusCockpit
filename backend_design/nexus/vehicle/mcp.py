# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
MCP Vehicle Bus Adapter — 通过 MCP SDK (Model Context Protocol) 对接车控服务

使用 mcp.ClientSession + mcp.StdioServerParameters 与车控服务通信。
保留 MCPStdioVehicleAdapter 同步接口不变，内部通过后台 asyncio 事件循环驱动 MCP SDK 异步调用。
"""

from __future__ import annotations

import asyncio
import atexit
import threading
from typing import Any

from nexus.core.logger import get_logger
from nexus.vehicle.base import BaseVehicleAdapter, VehicleCommandResult

logger = get_logger(__name__)


class _MCPBackgroundRunner:
    """在后台线程中运行 MCP SDK 的异步上下文。

    MCP SDK (mcp.ClientSession) 是异步的，而 MCPStdioVehicleAdapter 暴露同步接口。
    本类在后台 daemon 线程中运行一个 asyncio 事件循环，通过 run_coroutine_threadsafe
    将同步调用桥接到异步 MCP SDK。

    生命周期:
        1. __init__ 启动后台线程 + 事件循环
        2. 后台线程进入 stdio_client + ClientSession 上下文管理器
        3. 调用 session.initialize() + session.list_tools()
        4. 通过 asyncio.Event 保持上下文管理器存活
        5. close() 设置 Event 退出上下文管理器
    """

    def __init__(
        self,
        command: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        protocol_version: str = "2024-11-05",
        client_name: str = "NexusCockpit",
        client_version: str = "1.0.0",
        tool_timeout: float = 10.0,
    ):
        if not command:
            raise ValueError("MCP command is required")

        self._command_str = command[0]
        self._command_args = command[1:]
        self._cwd = cwd
        self._env = env
        self._protocol_version = protocol_version
        self._client_name = client_name
        self._client_version = client_version
        self._tool_timeout = tool_timeout

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: Any | None = None  # mcp.ClientSession
        self._available_tools: set[str] = set()
        self._initialized = threading.Event()
        self._init_error: Exception | None = None
        self._stop_event: asyncio.Event | None = None

        atexit.register(self.close)

        # 启动后台线程并等待初始化完成
        self._thread = threading.Thread(target=self._run, daemon=True, name="mcp-sdk-bg")
        self._thread.start()

        if not self._initialized.wait(timeout=30):
            raise TimeoutError("MCP SDK initialization timed out (30s)")
        if self._init_error:
            raise RuntimeError(f"MCP SDK initialization failed: {self._init_error}")

    def _run(self) -> None:
        """后台线程入口：创建事件循环并运行 MCP SDK 异步上下文。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            if not self._initialized.is_set():
                self._init_error = e
                self._initialized.set()
            logger.debug(f"MCP background loop ended: {e}")
        finally:
            self._loop.close()

    async def _main(self) -> None:
        """MCP SDK 主协程：管理 stdio_client + ClientSession 生命周期。"""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self._command_str,
            args=self._command_args,
            cwd=self._cwd,
            env=self._env,
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(
                read, write,
                read_timeout_seconds=self._tool_timeout,
            ) as session:
                # 初始化 MCP 会话
                await session.initialize()
                self._session = session

                # 列出可用工具
                try:
                    result = await session.list_tools()
                    self._available_tools = {
                        t.name for t in result.tools if hasattr(t, "name")
                    }
                    logger.info(
                        f"MCP SDK initialized, available tools: "
                        f"{self._available_tools or '(none)'}"
                    )
                except Exception as e:
                    logger.warning(f"MCP list_tools failed: {e}")

                # 通知初始化完成
                self._initialized.set()

                # 保持上下文管理器存活，直到 close() 被调用
                self._stop_event = asyncio.Event()
                await self._stop_event.wait()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """同步调用 MCP 工具（通过后台事件循环桥接到异步 session.call_tool）。

        Returns:
            mcp.CallToolResult 对象
        """
        if self._session is None or self._loop is None:
            raise RuntimeError("MCP session not initialized")

        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments),
            self._loop,
        )
        return future.result(timeout=self._tool_timeout)

    @property
    def available_tools(self) -> set[str]:
        return self._available_tools

    def close(self) -> None:
        """关闭 MCP SDK 会话和后台线程。"""
        if self._stop_event and self._loop:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                pass  # loop already closed
        if self._thread:
            self._thread.join(timeout=5)


class MCPStdioVehicleAdapter(BaseVehicleAdapter):
    """MCP stdio 车控适配器。

    使用 MCP SDK (mcp.ClientSession) 与车控服务通信，
    公共接口（vehicle_climate / vehicle_window 等）保持不变。
    """

    def __init__(
        self,
        command: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        protocol_version: str = "2024-11-05",
        client_name: str = "NexusCockpit",
        client_version: str = "1.0.0",
        tool_timeout: float = 10.0,
        validate_tools: bool = True,
    ):
        self._runner = _MCPBackgroundRunner(
            command=command,
            cwd=cwd,
            env=env,
            protocol_version=protocol_version,
            client_name=client_name,
            client_version=client_version,
            tool_timeout=tool_timeout,
        )
        self.tool_timeout = tool_timeout
        self.available_tools: set[str] = self._runner.available_tools if validate_tools else set()

    def vehicle_climate(
        self, op="status", target_temp=None, delta=None,
        fan_speed=None, mode=None,
    ) -> VehicleCommandResult:
        return self._call_tool("vehicle_climate", {
            "op": op, "target_temp": target_temp, "delta": delta,
            "fan_speed": fan_speed, "mode": mode,
        })

    def vehicle_window(self, op="status", position="all", percent=None) -> VehicleCommandResult:
        return self._call_tool("vehicle_window", {"op": op, "position": position, "percent": percent})

    def vehicle_seat(self, op="status", position="driver", level=None, direction=None) -> VehicleCommandResult:
        return self._call_tool("vehicle_seat", {"op": op, "position": position, "level": level, "direction": direction})

    def vehicle_navigation(self, destination, waypoint="", mode="drive") -> VehicleCommandResult:
        return self._call_tool("vehicle_navigation", {"destination": destination, "waypoint": waypoint, "mode": mode})

    def vehicle_media(self, op="play", source=None, track=None, volume=None) -> VehicleCommandResult:
        return self._call_tool("vehicle_media", {"op": op, "source": source, "track": track, "volume": volume})

    def vehicle_status(self) -> VehicleCommandResult:
        return self._call_tool("vehicle_status", {})

    def invoke_command(self, command_name: str, payload: dict[str, Any]) -> VehicleCommandResult:
        return self._call_tool(command_name, payload)

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> VehicleCommandResult:
        if self.available_tools and tool_name not in self.available_tools:
            return VehicleCommandResult(False, f"MCP server 不暴露工具: {tool_name}", error="tool_not_exposed")

        try:
            result = self._runner.call_tool(
                tool_name,
                {k: v for k, v in arguments.items() if v is not None},
            )
        except Exception as exc:
            return VehicleCommandResult(False, f"MCP 调用失败: {exc}", error="mcp_call_failed")

        return self._convert_result(result, tool_name)

    def _convert_result(self, result: Any, tool_name: str) -> VehicleCommandResult:
        """将 MCP SDK 的 CallToolResult 转换为 VehicleCommandResult。

        MCP SDK 的 CallToolResult 包含:
            - content: list[TextContent | ImageContent | ...]  (每个 item 有 .text 属性)
            - isError: bool
            - structuredContent: dict | None
        """
        if result is None:
            return VehicleCommandResult(True, f"MCP 工具 {tool_name} 已执行。")

        is_error = bool(getattr(result, "isError", False))

        # 提取文本内容
        text_parts: list[str] = []
        content = getattr(result, "content", [])
        if content:
            for item in content:
                text = getattr(item, "text", None)
                if text:
                    text_parts.append(str(text))
                elif isinstance(item, str):
                    text_parts.append(item)

        message = "\n".join(p for p in text_parts if p).strip()

        # 尝试从 structuredContent 获取消息
        structured = getattr(result, "structuredContent", None)
        if not message and isinstance(structured, dict):
            message = structured.get("message") or structured.get("summary") or ""
        if not message:
            message = f"MCP 工具 {tool_name} 已执行。"

        data: dict[str, Any] = {"raw": result}
        if structured is not None:
            data["structuredContent"] = structured

        err = "mcp_tool_error" if is_error else ""
        return VehicleCommandResult(
            success=not is_error, message=message,
            data=data, error=err,
        )

    def close(self) -> None:
        """关闭 MCP SDK 会话。"""
        self._runner.close()
