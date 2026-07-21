# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Lifestyle Expert — 生活推荐专家 Agent

封装生活类技能：联网搜索、外卖点餐、本地生活推荐。
"""

from __future__ import annotations

from typing import Any

from nexus.agent.experts.base import BaseExpertAgent
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup

logger = get_logger(__name__)


class LifestyleExpert(BaseExpertAgent):
    """生活推荐专家：处理搜索、点餐、本地推荐。"""

    expert_name = "lifestyle"
    group = SkillGroup.LIFESTYLE

    async def _execute(self, state: SupervisorState) -> dict[str, Any]:
        intent = state.get("intent", {})

        # 优先级 0: 高德 POI 周边搜索
        # 当用户询问"附近美食"、"周边加油站"等基于位置的信息时，
        # 使用高德 POI API 搜索，结果比 Tavily 通用搜索更准确
        poi_action = intent.get("Poi_Search_Action") or {}
        if poi_action and isinstance(poi_action, dict) and poi_action.get("keyword"):
            cockpit_id = state.get("cockpit_id", "")
            poi_kwargs = {
                "keyword": poi_action.get("keyword", ""),
                "poi_type": poi_action.get("poi_type", ""),
                "radius": poi_action.get("radius", 3000),
                "cockpit_id": cockpit_id,
            }
            result = await self.registry.execute("amap_poi_search", poi_kwargs)
            return self._build_expert_result(
                action="amap_poi_search",
                reply=result.message if result.status == "ok" else "",
                search_context=result.search_context if result.status == "ok" else "",
                handled=result.handled,
                skill_status=result.status,
            )

        # 优先级 1: 联网搜索
        search_query = intent.get("Need_Search") or ""
        if search_query and isinstance(search_query, str) and search_query.strip():
            result = await self.registry.execute("web_search", {"query": search_query.strip()})
            return self._build_expert_result(
                action="web_search",
                reply=result.message if result.status == "error" else "",
                search_context=result.search_context,
                handled=result.handled,
                skill_status=result.status,
            )

        # 优先级 2: 点餐
        if intent.get("Call_elm"):
            food_name = (intent.get("Food_candidate") or "").strip() or "随便来点"
            result = await self.registry.execute("order_food", {"food_name": food_name})
            return self._build_expert_result(
                action="order_food",
                reply=result.message,
                handled=result.handled,
                skill_status=result.status,
            )

        # 无匹配
        return self._build_expert_result(action="", reply="", handled=False)
