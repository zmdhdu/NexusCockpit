# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""Seat Control Skill"""

from __future__ import annotations
from typing import Any
from nexus.skills.base import SkillResult
from nexus.skills.vehicle import VehicleBaseSkill


class SeatControlSkill(VehicleBaseSkill):
    name = "vehicle_seat"
    tool_name = "vehicle_seat"
    description = "控制座椅加热、通风、按摩和位置调整。"
    required_parameters: list[str] = []
    optional_parameters = ["op", "position", "level", "direction"]
    examples = [
        {"input": "打开主驾座椅加热", "arguments": {"op": "heat_on", "position": "driver", "level": 1}},
        {"input": "副驾座椅通风开到2档", "arguments": {"op": "cool_on", "position": "passenger", "level": 2}},
        {"input": "打开按摩", "arguments": {"op": "massage_on", "position": "driver", "level": 1}},
    ]
    parameters = {
        "op": {"type": "string", "description": "操作类型，例如 heat_on、cool_on、massage_on、forward"},
        "position": {"type": "string", "description": "座椅位置，例如 driver、passenger"},
        "level": {"type": "integer", "description": "档位，例如 1 到 3"},
        "direction": {"type": "string", "description": "方向，例如 forward、backward"},
    }

    async def execute(self, **kwargs: Any) -> SkillResult:
        return self._invoke(kwargs)
