# Copyright (c) 2026 zmdhdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Health Expert — 车辆健康专家 Agent

封装车辆健康类技能：故障诊断、故障码翻译、保养建议。
依赖 Cherry 知识库（Phase 3 实现后生效）。
"""

from __future__ import annotations

from typing import Any

from nexus.agent.experts.base import BaseExpertAgent
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup

logger = get_logger(__name__)


class HealthExpert(BaseExpertAgent):
    """车辆健康专家：处理故障诊断、故障码翻译、保养建议。

    根据 intent["Health_Action"]["skill"] 路由到具体技能：
      - diagnose_vehicle: 车辆异常问题诊断
      - decode_dtc: 故障码翻译
      - maintenance_advice: 保养建议
    """

    expert_name = "health"
    group = SkillGroup.HEALTH

    async def _execute(self, state: SupervisorState) -> dict[str, Any]:
        intent = state.get("intent", {})
        health_action = intent.get("Health_Action") or {}
        user_input = state.get("user_input", "")

        if not health_action or not isinstance(health_action, dict):
            return self._build_expert_result(action="", reply="", handled=False)

        skill_name = health_action.get("skill", "diagnose_vehicle")

        # 根据技能名构建参数
        if skill_name == "diagnose_vehicle":
            kwargs = {"query": health_action.get("query", user_input)}
        elif skill_name == "decode_dtc":
            dtc_code = health_action.get("dtc_code", "")
            if not dtc_code:
                return self._build_expert_result(
                    action="", reply="请提供故障码。", handled=True
                )
            kwargs = {"dtc_code": dtc_code}
        elif skill_name == "maintenance_advice":
            kwargs = {
                "mileage": health_action.get("mileage", 0),
                "months": health_action.get("months", 0),
            }
        else:
            # 未知健康技能，默认走诊断
            skill_name = "diagnose_vehicle"
            kwargs = {"query": user_input}

        result = await self.registry.execute(skill_name, kwargs)
        return self._build_expert_result(
            action=skill_name,
            reply=result.message,
            search_context=result.search_context,
            handled=result.handled,
            skill_status=result.status,
        )
