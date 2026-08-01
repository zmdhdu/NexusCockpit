# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reviewer Node — 质量审查节点

职责: 调用 ReviewerAgent 对最终回复做质量评分和记忆存储

从 supervisor_graph.py 的 _reviewer_node() 方法抽取。

当前状态:
  - 依赖未完成的 context.py (NodeContext) 模块
  - 实际生产代码中此节点未被导入，ReviewerAgent 仍由 SupervisorGraph 直接调用
  - 节点拆分完成后此文件将正式启用

未来改进标记:
  - LangGraph END node: Reviewer 作为最终节点，
    可直接映射到 LangGraph END 节点 + 后置 hook
  - 循环依赖修复: 原 run() 委托回 SupervisorGraph._reviewer_node()，
    拆分完成后改为直接持有 ReviewerAgent 引用，消除循环依赖
"""

from __future__ import annotations

from typing import Any

from nexus.core.logger import get_logger

logger = get_logger(__name__)


class ReviewerNode:
    """质量审查节点 — 评分 + 记忆存储。

    拆分完成后将通过依赖注入获取 ReviewerAgent，
    不再委托回 SupervisorGraph（消除循环依赖）。

    Args:
        reviewer_agent: ReviewerAgent 实例（依赖注入）
        graph_ref: SupervisorGraph 引用（兼容旧委托模式，拆分完成后移除）
    """

    def __init__(self, reviewer_agent: Any = None, graph_ref: Any = None):
        self._reviewer_agent = reviewer_agent
        self._graph = graph_ref

    async def run(self, state: dict) -> dict[str, Any]:
        """执行质量审查。

        优先使用注入的 ReviewerAgent（消除循环依赖），
        兼容旧委托模式（委托回 SupervisorGraph._reviewer_node()）。
        """
        if self._reviewer_agent is not None:
            return await self._reviewer_agent.review(state)
        if self._graph is not None:
            return await self._graph._reviewer_node(state)
        raise RuntimeError(
            "ReviewerNode requires either reviewer_agent or graph_ref"
        )
