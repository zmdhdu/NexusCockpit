# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reviewer Node — 质量审查节点

职责: 调用 ReviewerAgent 对最终回复做质量评分和记忆存储

从 supervisor_graph.py 的 _reviewer_node() 方法抽取。

未来改进标记:
  - LangGraph END node: Reviewer 作为最终节点，
    可直接映射到 LangGraph END 节点 + 后置 hook
"""

from __future__ import annotations

from typing import Any

from nexus.agent.nodes.context import NodeContext
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class ReviewerNode:
    """质量审查节点 — 评分 + 记忆存储。"""

    def __init__(self, ctx: NodeContext, graph_ref: Any = None):
        self.ctx = ctx
        self._graph = graph_ref

    async def run(self, state: dict) -> dict[str, Any]:
        """执行质量审查。

        委托回 SupervisorGraph._reviewer_node()。
        """
        if self._graph is not None:
            return await self._graph._reviewer_node(state)
        raise RuntimeError("ReviewerNode requires graph_ref in delegate mode")
