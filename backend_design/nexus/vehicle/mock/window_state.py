# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""车窗状态模型 + 车窗控制方法。"""

from __future__ import annotations

from nexus.vehicle.base import VehicleCommandResult


class WindowState:
    """车窗状态管理。"""

    # 合法操作符枚举
    _VALID_OPS = frozenset({
        "open", "close", "set", "set_position", "move_to",
        "up", "down", "raise", "lower",
        "status", "query", "query_status",
    })

    # 合法位置枚举
    _VALID_POSITIONS = frozenset({
        "all", "front_left", "front_right",
        "rear_left", "rear_right", "sunroof",
    })

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
        # 操作符校验 — 非法 op 直接返回错误
        if op not in self._VALID_OPS:
            return VehicleCommandResult(
                success=False,
                message=f"不支持的车窗操作: {op}，请使用 open/close/set/status。",
                data={"windows": dict(self.windows)},
            )

        # 位置校验 — 非法 position 回退到 all
        if position not in self._VALID_POSITIONS:
            position = "all"

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
        elif op in ("open", "up", "raise"):
            value = 100
            if percent is not None:
                value = max(0, min(100, int(percent)))
        elif op in ("close", "down", "lower"):
            value = 0
            if percent is not None:
                value = max(0, min(100, int(percent)))
        else:
            value = self.windows.get(position, self.windows["all"])

        if position == "all":
            for key in self.windows:
                self.windows[key] = value
        else:
            self.windows[position] = value
            # 同步 all 字段为所有车窗的最大值
            self.windows["all"] = max(v for k, v in self.windows.items() if k != "all")

        return VehicleCommandResult(
            success=True,
            message=f"已将{position}车窗调整到 {value}%。",
            data={"windows": dict(self.windows)},
        )
