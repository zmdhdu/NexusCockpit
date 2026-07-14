# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
MCP Vehicle Bus Adapter — 通过 MCP (Model Context Protocol) 对接车控服务
使用 stdio JSON-RPC 传输层
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import shlex
import subprocess
import threading
import time
from typing import Any, Dict, Optional

from nexus.core.logger import get_logger
from nexus.vehicle.base import BaseVehicleAdapter, VehicleCommandResult

logger = get_logger(__name__)


class StdioJsonRpcTransport:
    """MCP stdio 传输层，使用 Content-Length framing"""

    def __init__(self, command: list[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None):
        if not command:
            raise ValueError("MCP command is required")

        self.command = command
        self.cwd = cwd or os.getcwd()
        self.env = env or os.environ.copy()
        self.process = subprocess.Popen(
            command, cwd=self.cwd, env=self.env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=0,
        )
        if not self.process.stdin or not self.process.stdout:
            raise RuntimeError("Failed to start MCP stdio process")

        self._stdin = self.process.stdin
        self._stdout = self.process.stdout
        self._stderr = self.process.stderr
        self._write_lock = threading.Lock()
        self._pending: Dict[int, queue.Queue] = {}
        self._pending_lock = threading.Lock()
        self._message_id = 0

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_thread.start()
        atexit.register(self.close)

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        request_id = self._next_id()
        response_queue: queue.Queue = queue.Queue(maxsize=1)

        with self._pending_lock:
            self._pending[request_id] = response_queue

        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})

        try:
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise TimeoutError(f"MCP request timed out: {method}") from exc

        if isinstance(response, dict) and "error" in response:
            error = response["error"]
            if isinstance(error, dict):
                raise RuntimeError(error.get("message") or str(error))
            raise RuntimeError(str(error))

        return response

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        try:
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                except Exception:
                    pass
        finally:
            for stream in (self._stdin, self._stdout, self._stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass

    def _next_id(self) -> int:
        self._message_id += 1
        return self._message_id

    def _send(self, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        framed = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
        with self._write_lock:
            self._stdin.write(framed)
            self._stdin.flush()

    def _read_loop(self) -> None:
        buffer = b""
        while True:
            try:
                chunk = self._stdout.read(4096)
            except Exception:
                break
            if not chunk:
                break
            buffer += chunk
            while True:
                message, buffer = self._extract_message(buffer)
                if message is None:
                    break
                request_id = message.get("id")
                if request_id is None:
                    continue
                with self._pending_lock:
                    response_queue = self._pending.pop(request_id, None)
                if response_queue is not None:
                    response_queue.put(message)

    def _stderr_loop(self) -> None:
        if not self._stderr:
            return
        while True:
            try:
                chunk = self._stderr.readline()
            except Exception:
                break
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace").rstrip()
            if text:
                logger.debug(f"[MCP STDERR] {text}")

    def _extract_message(self, buffer: bytes) -> tuple[Optional[Dict[str, Any]], bytes]:
        header_end = buffer.find(b"\r\n\r\n")
        if header_end < 0:
            return None, buffer

        header_blob = buffer[:header_end].decode("ascii", errors="replace")
        content_length = None
        for line in header_blob.split("\r\n"):
            if line.lower().startswith("content-length:"):
                try:
                    content_length = int(line.split(":", 1)[1].strip())
                except Exception:
                    content_length = None
                break

        if content_length is None:
            return None, buffer[header_end + 4:]

        body_start = header_end + 4
        body_end = body_start + content_length
        if len(buffer) < body_end:
            return None, buffer

        body = buffer[body_start:body_end]
        remainder = buffer[body_end:]
        try:
            message = json.loads(body.decode("utf-8", errors="replace"))
        except Exception:
            return None, remainder
        return message, remainder


class MCPStdioVehicleAdapter(BaseVehicleAdapter):
    """MCP stdio 车控适配器"""

    def __init__(
        self,
        command: list[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        protocol_version: str = "2024-11-05",
        client_name: str = "NexusCockpit",
        client_version: str = "1.0.0",
        tool_timeout: float = 10.0,
        validate_tools: bool = True,
    ):
        self.transport = StdioJsonRpcTransport(command=command, cwd=cwd, env=env)
        self.protocol_version = protocol_version
        self.client_name = client_name
        self.client_version = client_version
        self.tool_timeout = tool_timeout
        self.available_tools: set[str] = set()
        self._initialize()
        if validate_tools:
            self._refresh_tools()

    def _initialize(self) -> None:
        self.transport.request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {"roots": {"listChanged": False}, "sampling": {}, "experimental": {}},
                "clientInfo": {"name": self.client_name, "version": self.client_version},
            },
            timeout=self.tool_timeout,
        )
        try:
            self.transport.notify("notifications/initialized", {})
        except Exception:
            pass

    def _refresh_tools(self) -> None:
        try:
            response = self.transport.request("tools/list", {}, timeout=self.tool_timeout)
            payload = response.get("result", response) if isinstance(response, dict) else {}
            tools = payload.get("tools", []) if isinstance(payload, dict) else []
            self.available_tools = {t.get("name") for t in tools if isinstance(t, dict) and t.get("name")}
        except Exception as exc:
            logger.warning(f"MCP tools/list failed: {exc}")

    def vehicle_climate(self, op="status", target_temp=None, delta=None, fan_speed=None, mode=None) -> VehicleCommandResult:
        return self._call_tool("vehicle_climate", {"op": op, "target_temp": target_temp, "delta": delta, "fan_speed": fan_speed, "mode": mode})

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

    def invoke_command(self, command_name: str, payload: Dict[str, Any]) -> VehicleCommandResult:
        return self._call_tool(command_name, payload)

    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> VehicleCommandResult:
        if self.available_tools and tool_name not in self.available_tools:
            return VehicleCommandResult(False, f"MCP server 不暴露工具: {tool_name}", error="tool_not_exposed")

        try:
            response = self.transport.request(
                "tools/call",
                {"name": tool_name, "arguments": {k: v for k, v in arguments.items() if v is not None}},
                timeout=self.tool_timeout,
            )
        except Exception as exc:
            return VehicleCommandResult(False, f"MCP 调用失败: {exc}", error="mcp_call_failed")

        payload = response.get("result", response) if isinstance(response, dict) else response
        return self._convert_result(payload, tool_name)

    def _convert_result(self, response: Dict[str, Any], tool_name: str) -> VehicleCommandResult:
        if not isinstance(response, dict):
            return VehicleCommandResult(True, str(response), data={"raw": response})

        is_error = bool(response.get("isError", False))
        content = response.get("content", [])
        structured = response.get("structuredContent")
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                text_parts.append(str(item.get("text")))
            elif isinstance(item, str):
                text_parts.append(item)

        message = "\n".join(p for p in text_parts if p).strip()
        if not message and isinstance(structured, dict):
            message = structured.get("message") or structured.get("summary") or ""
        if not message:
            message = f"MCP 工具 {tool_name} 已执行。"

        data: Dict[str, Any] = {"raw": response}
        if structured is not None:
            data["structuredContent"] = structured

        return VehicleCommandResult(success=not is_error, message=message, data=data, error="mcp_tool_error" if is_error else "")
