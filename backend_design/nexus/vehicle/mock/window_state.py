# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""车窗状态模型 + 车窗控制方法。"""

from __future__ import annotations

from typing import Any

from nexus.vehicle.base import VehicleCommandResult


class WindowState:
    """车窗状态管理。"""

    def __init__(self):
        self.windows: dict[str, int] = {
            "all": 0,
            "front_left": 0,
            "front_right": 0,
            "rear_left": 0,
            "rear_right": 0,
            "sunroof": 0,
        }

    def handle(
        self, op: str = "status", position: str = "all", percent: int | None = None,
    ) -> VehicleCommandResult:
        if op in ("status", "query", "query_status"):
            return VehicleCommandResult(
                success=True,
                message=f"车窗状态：{self.windows}",
                data={"windows": dict(self.windows)},
            )

        if op in ("set_position", "set", "move_to"):
            if percent is not None:
                value = max(0, min(100, int(percent)))
            else:
                value = self.windows.get(position, self.windows["all"])
        else:
            value = 0 if op in ("close", "down", "lower") else 100
            if percent is not None:
                value = max(0, min(100, int(percent)))

        if position == "all":
            for key in self.windows:
                self.windows[key] = value
        elif position in self.windows:
            self.windows[position] = value
        else:
            position = "all"
            for key in self.windows:
                self.windows[key] = value

        return VehicleCommandResult(
            success=True,
            message=f"已将{position}车窗调整到 {value}%。",
            data={"windows": dict(self.windows)},
        )
