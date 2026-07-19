# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Vehicle Base Skill — 车载技能基类
统一通过 vehicle adapter 访问车控总线

通过 tenant_context 获取当前座舱的独立适配器实例，
确保 Agent 工作流中的车控操作也按座舱隔离。
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
        # 保存默认适配器（单例），运行时可能被 _get_adapter 覆盖
        self._default_adapter = adapter or build_vehicle_adapter()

    @property
    def adapter(self) -> BaseVehicleAdapter:
        """获取当前座舱的车控适配器（多座舱隔离）。"""
        try:
            from nexus.core.tenant_context import get_cockpit_id
            from nexus.vehicle.factory import get_cockpit_vehicle_adapter
            cockpit_id = get_cockpit_id()
            if cockpit_id:
                return get_cockpit_vehicle_adapter(cockpit_id)
        except Exception:
            pass
        return self._default_adapter

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
