"""Navigation Skill"""

from __future__ import annotations
from typing import Any
from nexus.skills.base import SkillResult
from nexus.skills.vehicle import VehicleBaseSkill


class NavigationSkill(VehicleBaseSkill):
    name = "vehicle_navigation"
    tool_name = "vehicle_navigation"
    description = "发起导航到目的地，可选途经点。也支持查询当前位置。"
    required_parameters: list[str] = []
    optional_parameters = ["destination", "waypoint", "mode", "op"]
    examples = [
        {"input": "导航到上海虹桥火车站", "arguments": {"destination": "上海虹桥火车站", "mode": "drive"}},
        {"input": "带我去公司", "arguments": {"destination": "公司", "mode": "drive"}},
        {"input": "我在哪里", "arguments": {"op": "location"}},
        {"input": "导航到机场，途经充电站", "arguments": {"destination": "机场", "waypoint": "充电站", "mode": "drive"}},
    ]
    parameters = {
        "destination": {"type": "string", "description": "目的地，例如 家、公司、充电站"},
        "waypoint": {"type": "string", "description": "途经点"},
        "mode": {"type": "string", "description": "导航模式，例如 drive、walk"},
        "op": {"type": "string", "description": "操作类型，location 表示查询当前位置"},
    }

    async def execute(self, **kwargs: Any) -> SkillResult:
        return self._invoke(kwargs)
