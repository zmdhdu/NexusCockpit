# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reviewer Agent — 记忆管理器持有者

SupervisorGraph 通过 self.reviewer.memory_manager 访问记忆管理器。
质量审查的实际逻辑已迁移到 nexus.agent.nodes.reviewer_node.ReviewerNode.run() 中。

原始 review() 方法已删除 — 它使用 state.final_response 属性访问，
但 SupervisorState 是 TypedDict（字典），属性访问会抛出 AttributeError。
实际审查逻辑由 ReviewerNode.run() 通过 state.get("final_response") 正确处理。
"""

from __future__ import annotations

from nexus.core.logger import get_logger
from nexus.memory.manager import MemoryManager

logger = get_logger(__name__)


class ReviewerAgent:
    """审查 Agent — 持有记忆管理器供 ReviewerNode 使用。

    Args:
        memory_manager: 记忆管理器（可选），用于后台记忆存储
    """

    def __init__(self, memory_manager: MemoryManager | None = None):
        self.memory_manager = memory_manager
