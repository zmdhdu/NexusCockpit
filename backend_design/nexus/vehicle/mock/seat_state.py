# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""座椅状态模型 + 座椅控制方法。"""

from __future__ import annotations

from typing import Any

from nexus.vehicle.base import VehicleCommandResult


class SeatState:
    """座椅状态管理。"""

    def __init__(self):
        self.seats: dict[str, dict[str, Any]] = {
            "driver": {"heat": 0, "cool": 0, "massage": False, "position": "neutral"},
            "passenger": {"heat": 0, "cool": 0, "massage": False, "position": "neutral"},
        }

    def handle(
        self,
        op: str = "status",
        position: str = "driver",
        level: int | None = None,
        direction: str | None = None,
    ) -> VehicleCommandResult:
        seat = self.seats.get(position, self.seats["driver"])
        if op in ("heat_on", "heat", "seat_heat"):
            seat["heat"] = max(1, int(level or 1))
            seat["cool"] = 0
        elif op in ("heat_off", "heat_stop"):
            seat["heat"] = 0
        elif op in ("cool_on", "cool", "seat_cool"):
            seat["cool"] = max(1, int(level or 1))
            seat["heat"] = 0
        elif op in ("cool_off", "cool_stop"):
            seat["cool"] = 0
        elif op in ("massage_on", "massage"):
            seat["massage"] = True
        elif op in ("massage_off", "stop_massage"):
            seat["massage"] = False
        elif op in ("forward", "backward", "forward_adjust", "back_adjust"):
            seat["position"] = direction or op

        self.seats[position] = seat
        return VehicleCommandResult(
            success=True,
            message=f"已调整{position}座椅状态。",
            data={"seats": dict(self.seats)},
        )
