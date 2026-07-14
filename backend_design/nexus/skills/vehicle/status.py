# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""Vehicle Status Skill"""

from __future__ import annotations
from typing import Any
from nexus.skills.base import SkillResult
from nexus.skills.vehicle import VehicleBaseSkill


class VehicleStatusSkill(VehicleBaseSkill):
    name = "vehicle_status"
    tool_name = "vehicle_status"
    description = "查询车辆状态，包括胎压、续航、电量、油量和保养信息。也支持查询当前位置。"
    required_parameters: list[str] = []
    optional_parameters = ["op"]
    examples = [
        {"input": "车辆状态怎么样", "arguments": {}},
        {"input": "查一下胎压和续航", "arguments": {}},
        {"input": "我在哪里", "arguments": {"op": "location"}},
    ]
    parameters = {
        "op": {"type": "string", "description": "操作类型，location 表示查询当前位置，status 表示查询车辆状态"},
    }

    async def execute(self, **kwargs: Any) -> SkillResult:
        cleaned = {k: v for k, v in kwargs.items() if v is not None}
        return self._invoke(cleaned)
