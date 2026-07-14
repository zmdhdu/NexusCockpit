# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Health Expert — 车辆健康专家 Agent

封装车辆健康类技能：故障诊断、故障码翻译、保养建议。
v2.0 新增专家，依赖 Cherry 知识库（Phase 3 实现后生效）。
"""

from __future__ import annotations

from typing import Any, Dict

from nexus.agent.experts.base import BaseExpertAgent
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup

logger = get_logger(__name__)


class HealthExpert(BaseExpertAgent):
    """车辆健康专家：处理故障诊断、故障码翻译、保养建议。

    v2.0 Phase 1 阶段为骨架实现，
    Phase 2/3 添加 diagnose_vehicle / decode_dtc / maintenance_advice 技能后自动生效。
    """

    expert_name = "health"
    group = SkillGroup.HEALTH

    async def _execute(self, state: SupervisorState) -> Dict[str, Any]:
        intent = state.get("intent", {})
        user_input = state.get("user_input", "")

        # 检查是否有车辆健康相关的技能可调用
        # Phase 2 添加技能后，这里会检查 intent 中的健康相关字段
        health_skill = self.registry.get_skill("diagnose_vehicle")
        if health_skill:
            result = await self.registry.execute("diagnose_vehicle", {"query": user_input})
            return self._build_expert_result(
                action="diagnose_vehicle",
                reply=result.message,
                search_context=result.search_context,
                handled=result.handled,
                skill_status=result.status,
            )

        # Phase 1 骨架：无健康技能时返回未处理
        return self._build_expert_result(action="", reply="", handled=False)
