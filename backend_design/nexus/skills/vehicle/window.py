"""Window Control Skill"""

from __future__ import annotations
from typing import Any
from nexus.skills.base import SkillResult
from nexus.skills.vehicle import VehicleBaseSkill


class WindowControlSkill(VehicleBaseSkill):
    name = "vehicle_window"
    tool_name = "vehicle_window"
    description = "控制车窗或天窗的开合、升降和百分比位置。"
    required_parameters: list[str] = []
    optional_parameters = ["op", "position", "percent"]
    examples = [
        {"input": "打开车窗", "arguments": {"op": "open", "position": "all", "percent": 100}},
        {"input": "关闭天窗", "arguments": {"op": "close", "position": "sunroof", "percent": 0}},
        {"input": "把左前窗调到一半", "arguments": {"op": "set_position", "position": "front_left", "percent": 50}},
    ]
    parameters = {
        "op": {"type": "string", "description": "操作类型，例如 open、close、up、down"},
        "position": {"type": "string", "description": "位置，例如 all、front_left、sunroof"},
        "percent": {"type": "integer", "description": "开合百分比，0 到 100"},
    }

    async def execute(self, **kwargs: Any) -> SkillResult:
        return self._invoke(kwargs)
