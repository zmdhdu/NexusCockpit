# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Agent 节点包 — SupervisorGraph 拆分后的各 LangGraph 节点

原 supervisor_graph.py (1800+ 行) 拆分为:
  - supervisor_node.py   → Supervisor 节点 (记忆召回 + 意图路由 + 专家分派)
  - dispatch_node.py     → 专家并行分派节点
  - responder_node.py    → 回复生成节点 (含工具合成)
  - reflection_node.py   → 反思校验节点 (含幻觉检查)
  - reviewer_node.py     → 质量审查节点

每个节点是独立的可测试单元，通过 NodeContext 共享依赖。
SupervisorGraph 瘦身为编排入口 (<200 行)，仅负责组装和调用。

未来改进标记:
  - LangGraph prebuilt: langgraph.prebuilt 中的 ToolNode/AgentExecutor
    可替换部分手写节点逻辑
  - LangGraph Command: LangGraph 1.x 的 Command 对象可简化条件路由
"""

from nexus.agent.nodes.supervisor_node import SupervisorNode
from nexus.agent.nodes.dispatch_node import DispatchNode
from nexus.agent.nodes.responder_node import ResponderNode
from nexus.agent.nodes.reflection_node import ReflectionNode
from nexus.agent.nodes.reviewer_node import ReviewerNode

__all__ = [
    "SupervisorNode",
    "DispatchNode",
    "ResponderNode",
    "ReflectionNode",
    "ReviewerNode",
]
