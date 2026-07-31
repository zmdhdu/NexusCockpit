# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Supervisor Node — Supervisor 节点

职责: 记忆召回 + 用户画像加载 + 意图路由 + 专家分派决策

从 supervisor_graph.py 的 _supervisor_node() 方法抽取。
当前采用委托模式，内部调用 SupervisorGraph 的方法，实现渐进式拆分。

未来改进标记:
  - LangGraph prebuilt Supervisor: 可用 langgraph.prebuilt 中的
    Supervisor 模式替换手写调度逻辑
  - DeepAgents: OpenAI DeepAgents 框架的 supervisor 角色可直接映射
"""

from __future__ import annotations

from typing import Any

from nexus.agent.nodes.context import NodeContext
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class SupervisorNode:
    """Supervisor 节点 — 记忆召回 + 意图路由 + 专家分派。

    采用委托模式：方法签名与 LangGraph 节点兼容，
    内部委托回 SupervisorGraph._supervisor_node()，
    后续逐步将逻辑迁移到此类中，降低回归风险。
    """

    def __init__(self, ctx: NodeContext, graph_ref: Any = None):
        """初始化 Supervisor 节点。

        Args:
            ctx: 节点共享上下文
            graph_ref: SupervisorGraph 实例引用（委托模式用）
        """
        self.ctx = ctx
        self._graph = graph_ref

    async def run(self, state: dict) -> dict[str, Any]:
        """执行 Supervisor 节点逻辑。

        委托回 SupervisorGraph._supervisor_node()，
        后续逐步将逻辑迁移到此类中。

        Args:
            state: LangGraph 状态

        Returns:
            状态更新字典
        """
        if self._graph is not None:
            return await self._graph._supervisor_node(state)
        raise RuntimeError("SupervisorNode requires graph_ref in delegate mode")

    @staticmethod
    def route(state: dict) -> str:
        """Supervisor 条件路由：需要分派专家时走 dispatch，否则直连 responder。

        从 SupervisorGraph._route_from_supervisor 迁移。
        """
        if state.get("need_clarification"):
            return "responder"
        if not state.get("active_experts"):
            return "responder"
        return "dispatch"
