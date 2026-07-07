"""
Executor Agent — 技能执行

Executor 是工作流的第二站，根据 Planner 路由的意图，调度对应的技能执行。

示例:
    意图: {"Skill": "climate", "Action": "set_temp", "target_temp": 24}
    Executor: 调用 ClimateSkill → 设置空调温度为 24°C → 返回执行结果
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from nexus.core.logger import get_logger
from nexus.models.state import AgentState
from nexus.skills.orchestrator import SkillOrchestrator

logger = get_logger(__name__)


class ExecutorAgent:
    """执行 Agent: 根据意图调度技能并执行。

    Args:
        skill_orchestrator: 技能编排器，负责分发意图到对应技能
    """

    def __init__(self, skill_orchestrator: SkillOrchestrator):
        self.orchestrator = skill_orchestrator

    async def execute(self, state: AgentState) -> AgentState:
        """根据意图调度技能执行。

        如果需要澄清 (need_clarification=True)，跳过执行。

        Args:
            state: 包含 intent 的 Agent 状态

        Returns:
            更新后的 state，包含 skill_result、skill_handled 等字段
        """
        t0 = perf_counter()

        if state.need_clarification:
            # 需要澄清，不执行技能
            state.skill_handled = False
            state.metadata["executor_latency_ms"] = round((perf_counter() - t0) * 1000, 2)
            return state

        try:
            result = await self.orchestrator.dispatch(state.intent)
            state.skill_result = result
            state.skill_handled = result.handled
            state.skill_action = result.action
            state.search_context = result.search_context
            state.metadata["executor_latency_ms"] = round((perf_counter() - t0) * 1000, 2)
            state.metadata["skill_action"] = result.action
            state.metadata["skill_metadata"] = result.metadata

            logger.info(
                f"Executor done: handled={result.handled}, action={result.action}, "
                f"latency={state.metadata['executor_latency_ms']}ms"
            )
        except Exception as e:
            logger.error(f"Executor failed: {e}")
            state.skill_handled = False
            state.metadata["executor_latency_ms"] = round((perf_counter() - t0) * 1000, 2)
            state.metadata["executor_error"] = str(e)

        return state
