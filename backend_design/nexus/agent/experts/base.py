# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Base Expert Agent — 专家 Agent 基类

所有专家 Agent 继承此类，实现 run() 方法。
run() 是 LangGraph 节点函数，接收完整 state，返回 partial update。
"""

from __future__ import annotations

from abc import ABC
from time import perf_counter
from typing import Any, Dict

from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.skills.base import SkillGroup
from nexus.skills.registry import SkillRegistry

logger = get_logger(__name__)


class BaseExpertAgent(ABC):
    """专家 Agent 基类。

    每个专家封装一组相关技能，通过 SkillRegistry 调用。
    专家不直接修改 state，而是返回 partial update 字典。

    Attributes:
        expert_name: 专家名称（用于日志和 active_experts 匹配）
        group: 技能分组（对应 SkillGroup 枚举）
        registry: 技能注册中心
    """

    expert_name: str = "base"
    group: SkillGroup = SkillGroup.CHAT

    def __init__(self, skill_registry: SkillRegistry):
        self.registry = skill_registry

    def is_active(self, state: SupervisorState) -> bool:
        """检查此专家是否在 Supervisor 分派的活跃列表中。"""
        return self.expert_name in state.get("active_experts", [])

    async def run(self, state: SupervisorState) -> Dict[str, Any]:
        """执行专家逻辑，返回 partial state update。

        如果专家不在 active_experts 中，返回空字典（no-op）。
        子类应实现 _execute() 方法封装具体逻辑。

        Args:
            state: 完整的 SupervisorState

        Returns:
            Partial state update 字典
        """
        if not self.is_active(state):
            return {}

        t0 = perf_counter()
        try:
            result = await self._execute(state)
            latency_ms = round((perf_counter() - t0) * 1000, 2)
            result.setdefault("metadata", {})["latency_ms"] = latency_ms

            logger.info(
                f"Expert '{self.expert_name}' done: "
                f"handled={result.get('skill_handled', False)}, "
                f"action={result.get('skill_action', '')}, "
                f"latency={latency_ms}ms"
            )
            return result
        except Exception as e:
            logger.error(f"Expert '{self.expert_name}' failed: {e}")
            return {
                "metadata": {
                    f"{self.expert_name}_error": str(e),
                    f"{self.expert_name}_latency_ms": round((perf_counter() - t0) * 1000, 2),
                }
            }

    async def _execute(self, state: SupervisorState) -> Dict[str, Any]:
        """子类实现：执行具体技能逻辑，返回 partial update。"""
        raise NotImplementedError

    def _build_expert_result(
        self,
        action: str,
        reply: str = "",
        search_context: str = "",
        handled: bool = True,
        skip_synthesis: bool = False,
        **extra: Any,
    ) -> Dict[str, Any]:
        """构建专家返回的 partial state update。

        同时写入 expert_results 列表（通过 reducer 累加）和
        兼容旧版的 skill_result / skill_action 字段。

        如果提供了 skill_data 且未设置 skip_synthesis，额外输出顶层
        tool_result 字段，供 Responder 做 Tool→LLM 合成和反思校验。

        Args:
            skip_synthesis: 如果为 True，不设置 tool_result，
                直接使用 reply 作为回复（跳过 LLM 合成和反思）。
                适用于车控等返回自然语言消息的技能。
        """
        result_entry = {
            "expert": self.expert_name,
            "action": action,
            "reply": reply,
            "search_context": search_context,
            "handled": handled,
            **extra,
        }
        update: Dict[str, Any] = {
            "expert_results": [result_entry],
            "skill_action": action,
            "skill_handled": handled,
            "search_context": search_context,
            "metadata": {
                f"{self.expert_name}_action": action,
                f"{self.expert_name}_handled": handled,
            },
        }
        # 将工具结果提升到顶层 state，供 Responder 合成和反思使用
        # skip_synthesis=True 时跳过（车控指令直接使用工具返回的自然语言消息）
        if not skip_synthesis and handled and (extra.get("skill_data") or reply):
            update["tool_result"] = {
                "tool_name": action,
                "message": reply,
                "data": extra.get("skill_data", {}),
                "handled": handled,
                "expert": self.expert_name,
            }
        return update
