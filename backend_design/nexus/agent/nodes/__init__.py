# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Agent 节点包 — SupervisorGraph 拆分后的各 LangGraph 节点

节点文件:
  - context.py           → NodeContext 共享依赖容器
  - supervisor_node.py   → Supervisor 节点 (记忆召回 + 意图路由 + 专家分派)
  - dispatch_node.py     → 专家并行分派节点
  - responder_node.py    → 回复生成节点 (含工具合成)
  - reflection_node.py   → 反思校验节点 (含幻觉检查)
  - reviewer_node.py     → 质量审查节点

架构说明:
  - supervisor_graph.py 仅保留初始化和入口调用 (~280 行)
  - 每个节点文件 150-400 行，职责单一
  - 节点间通过 NodeContext 传递依赖，无直接引用
  - LLM 调用统一使用 chat_model (ChatOpenAI.ainvoke)，AsyncOpenAI 客户端仅保留向后兼容
"""

from nexus.agent.nodes.context import NodeContext
from nexus.agent.nodes.dispatch_node import DispatchNode
from nexus.agent.nodes.reflection_node import ReflectionNode
from nexus.agent.nodes.responder_node import ResponderNode
from nexus.agent.nodes.reviewer_node import ReviewerNode
from nexus.agent.nodes.supervisor_node import SupervisorNode

__all__ = [
    "NodeContext",
    "SupervisorNode",
    "DispatchNode",
    "ResponderNode",
    "ReflectionNode",
    "ReviewerNode",
]
