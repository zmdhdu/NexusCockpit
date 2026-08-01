# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""空调状态模型 + 空调控制方法。"""

from __future__ import annotations

from typing import Any

from nexus.vehicle.base import VehicleCommandResult


class ClimateState:
    """空调状态管理。"""

    def __init__(self):
        self.climate: dict[str, Any] = {
            "temperature": 22,
            "fan_speed": 3,
            "mode": "auto",
            "power": True,
        }

    def handle(
        self,
        op: str = "status",
        target_temp: int | None = None,
        delta: int | None = None,
        fan_speed: int | None = None,
        mode: str | None = None,
    ) -> VehicleCommandResult:
        # 电源开关
        if op in ("power_on", "on", "open"):
            self.climate["power"] = True
            return VehicleCommandResult(
                success=True,
                message="空调已开启。",
                data={"climate": dict(self.climate)},
            )
        if op in ("power_off", "off", "close"):
            self.climate["power"] = False
            return VehicleCommandResult(
                success=True,
                message="空调已关闭。",
                data={"climate": dict(self.climate)},
            )

        if mode:
            self.climate["mode"] = mode
        if fan_speed is not None:
            self.climate["fan_speed"] = max(1, min(7, int(fan_speed)))
        if target_temp is not None:
            self.climate["temperature"] = max(16, min(30, int(target_temp)))
        elif delta:
            self.climate["temperature"] = max(16, min(30, self.climate["temperature"] + int(delta)))
        else:
            if op in ("temp_up", "up"):
                self.climate["temperature"] = min(30, self.climate["temperature"] + 1)
            elif op in ("temp_down", "down"):
                self.climate["temperature"] = max(16, self.climate["temperature"] - 1)

        return VehicleCommandResult(
            success=True,
            message=f"已将空调设置为 {self.climate['temperature']} 度，风量 {self.climate['fan_speed']} 档。",
            data={"climate": dict(self.climate)},
        )
