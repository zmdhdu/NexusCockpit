# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""车况状态模型 + 车况查询方法。"""

from __future__ import annotations

from typing import Any

from nexus.vehicle.base import VehicleCommandResult


class StatusState:
    """车况状态管理。"""

    def __init__(self):
        self.status: dict[str, Any] = {
            "tire_pressure": "normal",
            "range_km": 420,
            "fuel_percent": 58,
            "battery_percent": 76,
            "maintenance": "normal",
        }

    def handle(self, op: str = "status") -> VehicleCommandResult:
        """返回车况摘要。"""
        summary = (
            f"胎压{self.status['tire_pressure']}，续航{self.status['range_km']}公里，"
            f"油量{self.status['fuel_percent']}%，电量{self.status['battery_percent']}%，"
            f"保养状态{self.status['maintenance']}。"
        )
        return VehicleCommandResult(
            success=True,
            message=summary,
            data={"status": dict(self.status)},
        )
