# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""Climate Control Skill"""

from __future__ import annotations

from typing import Any

from nexus.skills.base import SkillResult
from nexus.skills.vehicle import VehicleBaseSkill


class ClimateControlSkill(VehicleBaseSkill):
    name = "vehicle_climate"
    tool_name = "vehicle_climate"
    description = "调整空调温度、风量和模式，例如升高温度、降低温度、设置风量。"
    required_parameters: list[str] = []
    optional_parameters = ["op", "target_temp", "delta", "fan_speed", "mode"]
    examples = [
        {"input": "有点冷，调高一点温度", "arguments": {"op": "temp_up", "delta": 1}},
        {"input": "把空调调到24度", "arguments": {"op": "set_temp", "target_temp": 24}},
        {"input": "风量调到3档", "arguments": {"op": "set_fan", "fan_speed": 3}},
        {"input": "切到自动空调", "arguments": {"op": "set_mode", "mode": "auto"}},
    ]
    parameters = {
        "op": {"type": "string", "description": "操作类型，例如 temp_up、temp_down、status"},
        "target_temp": {"type": "integer", "description": "目标温度，例如 24"},
        "delta": {"type": "integer", "description": "相对调节幅度，例如 +1 或 -1"},
        "fan_speed": {"type": "integer", "description": "风量档位，1 到 7"},
        "mode": {"type": "string", "description": "模式，例如 auto、cool、heat"},
    }

    async def execute(self, **kwargs: Any) -> SkillResult:
        return self._invoke(kwargs)
