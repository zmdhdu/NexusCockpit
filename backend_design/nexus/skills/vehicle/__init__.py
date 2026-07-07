"""
Vehicle Base Skill — 车载技能基类
统一通过 vehicle adapter 访问车控总线
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from nexus.skills.base import BaseSkill, SkillResult
from nexus.vehicle.base import BaseVehicleAdapter


class VehicleBaseSkill(BaseSkill):
    """车载技能基类"""

    tool_name: str = ""

    def __init__(self, adapter: Optional[BaseVehicleAdapter] = None):
        from nexus.vehicle.factory import build_vehicle_adapter
        self.adapter = adapter or build_vehicle_adapter()

    def _invoke(self, payload: Dict[str, Any]) -> SkillResult:
        """调用车控适配器"""
        result = self.adapter.invoke_command(self.tool_name, payload)
        return SkillResult(
            status="ok" if result.success else "error",
            message=result.message,
            data=result.data,
            error=result.error,
            action=self.tool_name,
            handled=True,
        )
