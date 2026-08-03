# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""座椅状态模型 + 座椅控制方法。"""

from __future__ import annotations

from typing import Any

from nexus.vehicle.base import VehicleCommandResult


class SeatState:
    """座椅状态管理。"""

    # 合法操作符枚举
    _VALID_OPS = frozenset({
        "heat_on", "heat", "seat_heat", "heat_off", "heat_stop",
        "cool_on", "cool", "seat_cool", "cool_off", "cool_stop",
        "massage_on", "massage", "massage_off", "stop_massage",
        "forward", "backward", "forward_adjust", "back_adjust",
        "status", "query", "query_status",
    })

    # 合法位置枚举
    _VALID_POSITIONS = frozenset({
        "driver", "passenger", "rear_left", "rear_right",
    })

    def __init__(self):
        self.seats: dict[str, dict[str, Any]] = {
            "driver": {"heat": 0, "cool": 0, "massage": False, "position": "neutral"},
            "passenger": {"heat": 0, "cool": 0, "massage": False, "position": "neutral"},
            "rear_left": {"heat": 0, "cool": 0, "massage": False, "position": "neutral"},
            "rear_right": {"heat": 0, "cool": 0, "massage": False, "position": "neutral"},
        }

    def handle(
        self,
        op: str = "status",
        position: str = "driver",
        level: int | None = None,
        direction: str | None = None,
    ) -> VehicleCommandResult:
        # 操作符校验 — 非法 op 直接返回错误
        if op not in self._VALID_OPS:
            return VehicleCommandResult(
                success=False,
                message=f"不支持的座椅操作: {op}",
                data={"seats": dict(self.seats)},
            )

        # 位置校验 — 非法 position 回退到 driver
        if position not in self._VALID_POSITIONS:
            position = "driver"

        # 状态查询直接返回
        if op in ("status", "query", "query_status"):
            return VehicleCommandResult(
                success=True,
                message=f"{position}座椅状态：{self.seats[position]}",
                data={"seats": dict(self.seats)},
            )

        seat = self.seats[position]

        if op in ("heat_on", "heat", "seat_heat"):
            seat["heat"] = max(1, min(3, int(level or 1)))
            seat["cool"] = 0
        elif op in ("heat_off", "heat_stop"):
            seat["heat"] = 0
        elif op in ("cool_on", "cool", "seat_cool"):
            seat["cool"] = max(1, min(3, int(level or 1)))
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
