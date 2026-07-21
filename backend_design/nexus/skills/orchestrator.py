# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Skill Orchestrator — 技能编排器

根据意图路由的结果，将请求分发到对应技能执行。
是 Executor Agent 和 SkillRegistry 之间的中间层。

分发逻辑:
  1. 车控类: 检查 Climate/Window/Seat/Navigation/Media/Status 动作
  2. 点餐类: 检查 Call_elm 字段
  3. 搜索类: 检查 Need_Search 字段
  4. 注册类: 检查 Register_Action 字段
  5. 无匹配: 返回 handled=False，交由 LLM 兜底
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from nexus.core.logger import get_logger
from nexus.skills.base import SkillResult
from nexus.skills.registry import SkillRegistry

logger = get_logger(__name__)


@dataclass
class DispatchResult:
    """技能分发统一结果"""
    handled: bool = False
    action: str = ""
    reply: str = ""
    search_context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # 是否有副作用: 车控类技能会修改车辆硬件状态，标记后禁止缓存
    has_side_effect: bool = False


class SkillOrchestrator:
    """技能编排器: 根据意图分发到对应技能。

    Args:
        skill_registry: 技能注册中心
    """

    def __init__(self, skill_registry: SkillRegistry):
        self.registry = skill_registry

    async def _timed_execute(self, tool_name: str, payload: dict[str, Any]) -> tuple[SkillResult, float]:
        """执行技能并记录耗时"""
        t0 = perf_counter()
        result = await self.registry.execute(tool_name, payload)
        duration_ms = round((perf_counter() - t0) * 1000, 2)
        return result, duration_ms

    async def dispatch(self, intent: dict[str, Any]) -> DispatchResult:
        """
        根据意图结果分发到对应技能
        intent 格式参考 IntentRouterService 的输出
        """
        # 车控类: 逐个检查是否有对应的 action
        action_map = {
            "Climate_Action": "vehicle_climate",
            "Window_Action": "vehicle_window",
            "Seat_Action": "vehicle_seat",
            "Navigation_Action": "vehicle_navigation",
            "Media_Action": "vehicle_media",
            "Vehicle_Status_Action": "vehicle_status",
        }

        for intent_key, tool_name in action_map.items():
            action_data = intent.get(intent_key) or {}
            if action_data:
                result, duration = await self._timed_execute(tool_name, action_data)
                return DispatchResult(
                    handled=True,
                    action=tool_name,
                    reply=result.message,
                    metadata={
                        "intent": action_data,
                        "tool_name": tool_name,
                        "tool_duration_ms": duration,
                        **result.metadata,
                    },
                    has_side_effect=True,  # 车控指令有副作用，禁止缓存
                )

        # 点餐
        if intent.get("Call_elm"):
            food_name = (intent.get("Food_candidate") or "").strip() or "随便来点"
            result, duration = await self._timed_execute("order_food", {"food_name": food_name})
            return DispatchResult(
                handled=True,
                action="order_food",
                reply=result.message,
                metadata={"tool_name": "order_food", "tool_duration_ms": duration, "food_name": food_name},
            )

        # 联网搜索
        if intent.get("Need_Search"):
            query = (intent.get("Need_Search") or "").strip()
            if not query:
                return DispatchResult(handled=True, action="web_search", reply="你想查什么呀？")
            result, duration = await self._timed_execute("web_search", {"query": query})
            return DispatchResult(
                handled=True,
                action="web_search",
                search_context=result.search_context,
                reply=result.message if result.status == "error" else "",
                metadata={"query": query, "tool_name": "web_search", "tool_duration_ms": duration},
            )

        # 声纹注册
        register_name: str | None = intent.get("Register_Action")
        if register_name:
            result, duration = await self._timed_execute("register_voice", {"user_name": register_name})
            return DispatchResult(
                handled=True,
                action="register_voice",
                reply=result.message,
                metadata={"tool_name": "register_voice", "tool_duration_ms": duration, "user_name": register_name},
            )

        # 无匹配技能，交由 LLM 兜底
        return DispatchResult(handled=False)
