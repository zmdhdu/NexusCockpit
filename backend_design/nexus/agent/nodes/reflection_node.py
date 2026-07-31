# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reflection Node — 反思校验节点

职责: 对 LLM 输出做事实性/一致性/无幻觉检查，不通过时自动修正

从 supervisor_graph.py 的以下方法抽取:
  - _reflection_node()
  - _deterministic_date_check()
  - _reflect_search_response()
  - _reflect_chat_response()
  - _pre_check_chat_response()
  - _post_check_chat_response()
  - _is_hallucinated_history()
  - _regenerate_with_feedback()

未来改进标记:
  - LangGraph self-reflection: LangGraph 原生支持条件边循环实现
    "反思→修正→再检查" 流程，可替换手写的 _reflection_node 逻辑
  - DeepAgents reflection: DeepAgents 框架内置 reflection 机制
"""

from __future__ import annotations

from typing import Any

from nexus.agent.nodes.context import NodeContext
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class ReflectionNode:
    """反思校验节点 — 事实性检查 + 幻觉检测 + 自动修正。"""

    def __init__(self, ctx: NodeContext, graph_ref: Any = None):
        self.ctx = ctx
        self._graph = graph_ref

    async def run(self, state: dict) -> dict[str, Any]:
        """执行反思校验。

        委托回 SupervisorGraph._reflection_node()。
        """
        if self._graph is not None:
            return await self._graph._reflection_node(state)
        raise RuntimeError("ReflectionNode requires graph_ref in delegate mode")

    def pre_check(self, state: dict) -> str | None:
        """预检：在 LLM 生成前做确定性检查。

        委托回 SupervisorGraph._pre_check_chat_response()。
        """
        if self._graph is not None:
            return self._graph._pre_check_chat_response(state)
        return None

    def post_check(self, state: dict, response: str) -> str | None:
        """后检：对 LLM 生成结果做事实性/一致性检查。

        委托回 SupervisorGraph._post_check_chat_response()。
        """
        if self._graph is not None:
            return self._graph._post_check_chat_response(state, response)
        return None

    async def regenerate_with_feedback(self, state: dict) -> str:
        """带反馈的重新生成。

        委托回 SupervisorGraph._regenerate_with_feedback()。
        """
        if self._graph is not None:
            return await self._graph._regenerate_with_feedback(state)
        raise RuntimeError("ReflectionNode requires graph_ref in delegate mode")
