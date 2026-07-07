"""Vehicle Status Skill"""

from __future__ import annotations
from typing import Any
from nexus.skills.base import SkillResult
from nexus.skills.vehicle import VehicleBaseSkill


class VehicleStatusSkill(VehicleBaseSkill):
    name = "vehicle_status"
    tool_name = "vehicle_status"
    description = "查询车辆状态，包括胎压、续航、电量、油量和保养信息。"
    required_parameters: list[str] = []
    optional_parameters: list[str] = []
    examples = [
        {"input": "车辆状态怎么样", "arguments": {}},
        {"input": "查一下胎压和续航", "arguments": {}},
    ]
    parameters: dict = {}

    async def execute(self, **kwargs: Any) -> SkillResult:
        return self._invoke({})
