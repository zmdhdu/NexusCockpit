# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Navigation Expert — 导航专家 Agent

封装导航技能：目的地设置、路线规划、途经点、当前位置查询。

注: 查询位置时，从 adapter 缓存中读取 GPS 坐标传入工具，
    避免 IP 定位超时导致"未知位置"
"""

from __future__ import annotations

from typing import Any

from nexus.agent.experts.base import BaseExpertAgent
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup

logger = get_logger(__name__)


class NavExpert(BaseExpertAgent):
    """导航专家：处理导航目的地设置、路线规划和当前位置查询。"""

    expert_name = "navigation"
    group = SkillGroup.NAVIGATION

    async def _execute(self, state: SupervisorState) -> dict[str, Any]:
        intent = state.get("intent", {})
        nav_action = intent.get("Navigation_Action") or {}

        if not nav_action:
            return self._build_expert_result(action="", reply="", handled=False)

        # 过滤 None 值
        cleaned = {k: v for k, v in nav_action.items() if v is not None}

        # 查询位置时，从 adapter 缓存中读取 GPS 坐标传入工具
        # 避免 IP 定位超时导致"未知位置"
        op = cleaned.get("op", "")
        if op in ("location", "current_location", "where", "位置", "我在哪"):
            try:
                from nexus.vehicle.factory import get_cockpit_vehicle_adapter
                cockpit_id = state.get("cockpit_id", "")
                if cockpit_id:
                    adapter = get_cockpit_vehicle_adapter(cockpit_id)
                    if adapter and hasattr(adapter, "navigation"):
                        lat = adapter.navigation.get("latitude")
                        lon = adapter.navigation.get("longitude")
                        if lat is not None and lon is not None:
                            cleaned["latitude"] = lat
                            cleaned["longitude"] = lon
                            logger.info(
                                f"NavExpert: injected cached GPS coords "
                                f"({lat}, {lon}) into location query"
                            )
                        else:
                            logger.warning(
                                f"NavExpert: no cached GPS coords in adapter "
                                f"(cockpit_id={cockpit_id}), will fall back to IP location"
                            )
                else:
                    logger.warning("NavExpert: cockpit_id is empty, cannot get vehicle adapter for GPS coords")
            except Exception as e:
                logger.debug(f"NavExpert: failed to get cached GPS coords: {e}")

        result = await self.registry.execute("vehicle_navigation", cleaned)

        # 结果验证
        verified_reply = self._verify_result(result, action="vehicle_navigation")

        return self._build_expert_result(
            action="vehicle_navigation",
            reply=verified_reply,
            handled=result.handled,
            skill_status=result.status,
            skill_data=result.data,
        )

    def _verify_result(self, result: Any, action: str = "") -> str:
        """验证导航技能执行结果。

        检查项:
            - 执行状态是否为 ok
            - 结果消息是否为空
        """
        if result.status == "error":
            logger.warning(f"NavExpert verify: skill '{action}' returned error: {result.message}")
            return result.message or "导航服务暂时不可用，请稍后重试。"
        if not result.message or len(result.message.strip()) < 2:
            logger.warning(f"NavExpert verify: skill '{action}' returned empty message")
            return "导航指令已执行，但未返回详细信息。"
        return result.message
