"""
Vehicle Expert — 车控专家 Agent

封装车控类技能：空调/车窗/座椅/媒体/状态查询。
从 intent 中提取车控动作字段，分发到对应技能执行。
"""

from __future__ import annotations

from typing import Any, Dict

from nexus.agent.experts.base import BaseExpertAgent
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup

logger = get_logger(__name__)

# intent 字段 → 技能名映射
_VEHICLE_ACTION_MAP = {
    "Climate_Action": "vehicle_climate",
    "Window_Action": "vehicle_window",
    "Seat_Action": "vehicle_seat",
    "Media_Action": "vehicle_media",
    "Vehicle_Status_Action": "vehicle_status",
}


class VehicleExpert(BaseExpertAgent):
    """车控专家：处理空调/车窗/座椅/媒体/状态查询。"""

    expert_name = "vehicle"
    group = SkillGroup.VEHICLE

    async def _execute(self, state: SupervisorState) -> Dict[str, Any]:
        intent = state.get("intent", {})

        for intent_key, tool_name in _VEHICLE_ACTION_MAP.items():
            action_data = intent.get(intent_key) or {}
            if action_data:
                # 过滤 None 值
                cleaned = {k: v for k, v in action_data.items() if v is not None}
                result = await self.registry.execute(tool_name, cleaned)

                return self._build_expert_result(
                    action=tool_name,
                    reply=result.message,
                    handled=result.handled,
                    skill_status=result.status,
                    skill_data=result.data,
                )

        # 无匹配车控动作
        return self._build_expert_result(
            action="",
            reply="",
            handled=False,
        )
