# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Responder Node — 回复生成节点

职责: 调用 ResponderAgent 生成最终回复，含工具合成和流式输出

从 supervisor_graph.py 的 _responder_node() 和 _synthesize_tool_response() 抽取。

未来改进标记:
  - LangGraph ToolNode: langgraph.prebuilt.ToolNode 可替换手写的
    工具合成逻辑 (_synthesize_tool_response)
  - LangGraph Command: 使用 Command 对象管理流式输出状态
"""

from __future__ import annotations

from typing import Any

from nexus.agent.nodes.context import NodeContext
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class ResponderNode:
    """回复生成节点 — 调用 ResponderAgent 生成最终回复。"""

    def __init__(self, ctx: NodeContext, graph_ref: Any = None):
        self.ctx = ctx
        self._graph = graph_ref

    async def run(self, state: dict) -> dict[str, Any]:
        """执行回复生成。

        委托回 SupervisorGraph._responder_node()。
        """
        if self._graph is not None:
            return await self._graph._responder_node(state)
        raise RuntimeError("ResponderNode requires graph_ref in delegate mode")

    async def synthesize_tool_response(self, state: dict) -> str:
        """工具调用结果合成自然语言回复。

        委托回 SupervisorGraph._synthesize_tool_response()。
        """
        if self._graph is not None:
            return await self._graph._synthesize_tool_response(state)
        raise RuntimeError("ResponderNode requires graph_ref in delegate mode")
