# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Planner Agent — 意图规划与记忆召回

Planner 是 Multi-Agent 工作流的第一站，负责:
  1. 记忆召回 — 从用户历史记忆中检索相关信息
  2. 意图路由 — 判断用户想做什么 (车控/闲聊/搜索)
  3. 澄清判断 — 如果信息不足，生成澄清提问

示例:
    用户: "把空调调到24度"
    Planner: 召回记忆 → 路由到 climate_intent → 不需要澄清
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Dict

from nexus.core.logger import get_logger
from nexus.intent.router import IntentRouterService
from nexus.memory.manager import MemoryManager
from nexus.models.state import AgentState

logger = get_logger(__name__)


class PlannerAgent:
    """规划 Agent: 召回记忆 + 路由意图。

    Args:
        intent_router: 意图路由服务
        memory_manager: 记忆管理器
    """

    def __init__(
        self,
        intent_router: IntentRouterService,
        memory_manager: MemoryManager,
    ):
        self.intent_router = intent_router
        self.memory_manager = memory_manager

    async def plan(self, state: AgentState) -> AgentState:
        """执行规划: 召回记忆 → 路由意图。

        Args:
            state: 包含 user_input 和 user_id 的 Agent 状态

        Returns:
            更新后的 state，包含 recalled_memories、intent 等字段
        """
        t0 = perf_counter()

        # 1. 召回记忆
        try:
            memories = await self.memory_manager.recall(state.user_input, state.user_id, top_k=5)
            state.recalled_memories = memories
            state.memory_str = (
                f"【关于 {state.user_id} 的记忆】: {';'.join(memories)}"
                if memories
                else ""
            )
        except Exception as e:
            logger.error(f"Memory recall failed: {e}")
            state.recalled_memories = []
            state.memory_str = ""

        # 2. 意图路由
        try:
            intent = await self.intent_router.route(state.user_input)
            state.intent = intent
            state.intent_source = intent.get("Route_Source", "default")
            state.need_clarification = intent.get("Need_Clarification", False)
            state.clarification_prompt = intent.get("Clarification_Prompt", "")
        except Exception as e:
            logger.error(f"Intent routing failed: {e}")
            state.intent = {}
            state.intent_source = "error"

        state.metadata["planner_latency_ms"] = round((perf_counter() - t0) * 1000, 2)
        logger.info(
            f"Planner done: source={state.intent_source}, "
            f"clarify={state.need_clarification}, "
            f"latency={state.metadata['planner_latency_ms']}ms"
        )
        return state
