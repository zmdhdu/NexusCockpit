# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""空调状态模型 + 空调控制方法。

修复记录:
    - power_on/power_off 不再提前 return，而是继续执行后续参数设置逻辑，
      解决"打开空调温度22度风速1"只回复"空调已开启"但温度/风量未生效的问题。
"""

from __future__ import annotations

from typing import Any

from nexus.core.logger import get_logger
from nexus.vehicle.base import VehicleCommandResult

logger = get_logger(__name__)


class ClimateState:
    """空调状态管理。"""

    # 合法操作符枚举
    _VALID_OPS = frozenset({
        "power_on", "power_off", "on", "off", "open", "close",
        "temp_up", "temp_down", "up", "down", "set_temp",
        "set_fan", "set_mode", "set_fan_speed",
        "status", "query", "query_status",
    })

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
        """处理空调控制指令。

        执行顺序:
            1. 电源操作 (power_on/power_off) — 仅修改 power 状态，不提前返回
            2. 参数设置 (mode/fan_speed/target_temp/delta) — 无论电源状态如何都执行
            3. 温度微调 (temp_up/temp_down) — 无显式 target_temp 时按 delta 调整
            4. 状态查询 (status) — 返回当前状态

        这样设计确保 "打开空调温度22度风速1" 这类复合指令能同时生效电源+温度+风量。
        """
        # 操作符校验 — 非法 op 直接返回错误
        if op not in self._VALID_OPS:
            return VehicleCommandResult(
                success=False,
                message=f"不支持的空调操作: {op}",
                error="invalid_op",
                data={"climate": dict(self.climate)},
            )

        # 记录是否有电源操作
        power_changed = False
        power_message = ""

        # 1. 电源开关 — 不再提前 return，继续执行后续参数设置
        if op in ("power_on", "on", "open"):
            self.climate["power"] = True
            power_changed = True
            power_message = "空调已开启"
        elif op in ("power_off", "off", "close"):
            self.climate["power"] = False
            power_changed = True
            power_message = "空调已关闭"

        # 2. 参数设置 — 无论电源操作如何都执行
        if mode:
            self.climate["mode"] = mode
        if fan_speed is not None:
            self.climate["fan_speed"] = max(1, min(7, int(fan_speed)))
        if target_temp is not None:
            self.climate["temperature"] = max(16, min(30, int(target_temp)))
        elif delta:
            self.climate["temperature"] = max(16, min(30, self.climate["temperature"] + int(delta)))
        else:
            # 无显式 target_temp/delta 时，检查 op 是否为温度微调
            if op in ("temp_up", "up"):
                self.climate["temperature"] = min(30, self.climate["temperature"] + 1)
            elif op in ("temp_down", "down"):
                self.climate["temperature"] = max(16, self.climate["temperature"] - 1)

        # 3. 状态查询 — 直接返回当前状态
        if op in ("status", "query", "query_status"):
            return VehicleCommandResult(
                success=True,
                message=f"空调状态：温度 {self.climate['temperature']} 度，风量 {self.climate['fan_speed']} 档，模式 {self.climate['mode']}。",
                data={"climate": dict(self.climate)},
            )

        # 4. 构建回复消息 — 包含电源操作 + 参数设置的完整信息
        parts = []
        if power_changed:
            parts.append(power_message)

        # 如果有参数变更，追加参数信息（电源关闭时不显示参数）
        if self.climate["power"]:
            if target_temp is not None or delta or op in ("temp_up", "temp_down", "up", "down"):
                parts.append(f"温度已设为 {self.climate['temperature']} 度")
            if fan_speed is not None:
                parts.append(f"风量已设为 {self.climate['fan_speed']} 档")
            if mode:
                mode_names = {"auto": "自动", "cool": "制冷", "heat": "制热", "defog": "除雾", "vent": "通风", "defrost": "除霜"}
                parts.append(f"模式已设为 {mode_names.get(mode, mode)}")

        # 如果只有电源操作且无参数变更，使用简洁消息
        if not parts:
            parts.append(f"空调已开启，当前温度 {self.climate['temperature']} 度，风量 {self.climate['fan_speed']} 档。")

        message = "，".join(parts) + "。" if parts else "空调已开启。"

        return VehicleCommandResult(
            success=True,
            message=message,
            data={"climate": dict(self.climate)},
        )
