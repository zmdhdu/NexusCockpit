# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
HTTP Vehicle Bus Adapter — 通过 HTTP/REST 对接真实车控服务
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from nexus.core.logger import get_logger
from nexus.vehicle.base import BaseVehicleAdapter, VehicleCommandResult

logger = get_logger(__name__)


class HttpVehicleBusAdapter(BaseVehicleAdapter):
    """HTTP/REST 车控适配器"""

    def __init__(
        self,
        base_url: str,
        *,
        protocol: str = "rest",
        endpoint: str = "/vehicle/tools/invoke",
        timeout: float = 5.0,
        auth_token: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.protocol = protocol.strip().lower()
        self.endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        self.timeout = timeout
        self.auth_token = auth_token

    def vehicle_climate(
        self, op="status", target_temp=None, delta=None,
        fan_speed=None, mode=None,
    ) -> VehicleCommandResult:
        return self._invoke("vehicle_climate", {
            "op": op, "target_temp": target_temp, "delta": delta,
            "fan_speed": fan_speed, "mode": mode,
        })

    def vehicle_window(self, op="status", position="all", percent=None) -> VehicleCommandResult:
        return self._invoke("vehicle_window", {"op": op, "position": position, "percent": percent})

    def vehicle_seat(self, op="status", position="driver", level=None, direction=None) -> VehicleCommandResult:
        return self._invoke("vehicle_seat", {"op": op, "position": position, "level": level, "direction": direction})

    def vehicle_navigation(self, destination, waypoint="", mode="drive") -> VehicleCommandResult:
        return self._invoke("vehicle_navigation", {"destination": destination, "waypoint": waypoint, "mode": mode})

    def vehicle_media(self, op="play", source=None, track=None, volume=None) -> VehicleCommandResult:
        return self._invoke("vehicle_media", {"op": op, "source": source, "track": track, "volume": volume})

    def vehicle_status(self) -> VehicleCommandResult:
        return self._invoke("vehicle_status", {})

    def invoke_command(self, command_name: str, payload: dict[str, Any]) -> VehicleCommandResult:
        cleaned = {k: v for k, v in (payload or {}).items() if v is not None}
        return self._invoke(command_name, cleaned)

    def _invoke(self, tool_name: str, payload: dict[str, Any]) -> VehicleCommandResult:
        body = self._build_body(tool_name, payload)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        req = urllib_request.Request(
            self.base_url + self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return self._parse_response(raw, tool_name)
        except urllib_error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            return VehicleCommandResult(False, f"车控服务 HTTP 错误: {exc.code}", error=raw)
        except urllib_error.URLError as exc:
            return VehicleCommandResult(False, f"无法连接真实车控服务: {exc.reason}", error="connection_failed")
        except Exception as exc:
            return VehicleCommandResult(False, f"调用真实车控服务失败: {exc}", error="invoke_failed")

    def _build_body(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.protocol == "jsonrpc":
            return {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": tool_name, "params": payload}
        return {"tool": tool_name, "arguments": payload}

    def _parse_response(self, raw: str, tool_name: str) -> VehicleCommandResult:
        try:
            data = json.loads(raw)
        except Exception:
            return VehicleCommandResult(False, raw[:300] or f"非 JSON 响应: {tool_name}", error="invalid_response")

        if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
            data = data["result"]

        if isinstance(data, dict):
            if "success" in data or "message" in data:
                return VehicleCommandResult(
                    success=bool(data.get("success", True)),
                    message=str(data.get("message", "")),
                    data=data.get("data", {}) if isinstance(data.get("data", {}), dict) else {"raw": data.get("data")},
                    error=str(data.get("error", "")),
                )
            if "error" in data:
                error_block = data["error"]
                if isinstance(error_block, dict):
                    msg = str(error_block.get("message", "车控服务返回错误"))
                    return VehicleCommandResult(
                        False, msg, error=str(error_block),
                    )
                return VehicleCommandResult(False, str(error_block), error=str(error_block))
            return VehicleCommandResult(True, "车控服务执行成功。", data=data)

        return VehicleCommandResult(True, str(data), data={"raw": data})
