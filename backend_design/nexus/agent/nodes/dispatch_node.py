# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Dispatch Node — 专家并行分派节点

职责: 根据 Supervisor 设置的 active_experts，并行调用对应专家 Agent

从 supervisor_graph.py 的 _dispatch_node() 方法抽取。

未来改进标记:
  - LangGraph parallel nodes: LangGraph 原生支持并行节点执行，
    可用 add_node() 注册多个专家节点 + 条件边自动并行
    替代手写的 asyncio.gather 分派逻辑
"""

from __future__ import annotations

from typing import Any

from nexus.agent.nodes.context import NodeContext
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class DispatchNode:
    """专家分派节点 — 并行执行活跃专家。"""

    def __init__(self, ctx: NodeContext, graph_ref: Any = None):
        self.ctx = ctx
        self._graph = graph_ref

    async def run(self, state: dict) -> dict[str, Any]:
        """执行专家并行分派。

        委托回 SupervisorGraph._dispatch_node()。
        """
        if self._graph is not None:
            return await self._graph._dispatch_node(state)
        raise RuntimeError("DispatchNode requires graph_ref in delegate mode")
