# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Agent 节点包 — SupervisorGraph 拆分后的各 LangGraph 节点

原 supervisor_graph.py (2000+ 行) 计划拆分为:
  - supervisor_node.py   → Supervisor 节点 (记忆召回 + 意图路由 + 专家分派)
  - dispatch_node.py     → 专家并行分派节点
  - responder_node.py    → 回复生成节点 (含工具合成)
  - reflection_node.py   → 反思校验节点 (含幻觉检查)
  - reviewer_node.py     → 质量审查节点

当前状态:
  - supervisor_node.py / dispatch_node.py / responder_node.py / reflection_node.py
    尚未创建（计划在 P0-2 阶段从 supervisor_graph.py 拆出）
  - reviewer_node.py 已创建但依赖未完成的 context.py
  - 此 __init__.py 不导入不存在的模块，避免包 import 崩溃

未来改进标记:
  - 节点拆分完成后，取消下方注释，恢复 __all__ 导出
  - LangGraph prebuilt: langgraph.prebuilt 中的 ToolNode/AgentExecutor
    可替换部分手写节点逻辑
  - LangGraph Command: LangGraph 1.x 的 Command 对象可简化条件路由
"""

# 节点拆分完成后取消注释:
# from nexus.agent.nodes.supervisor_node import SupervisorNode
# from nexus.agent.nodes.dispatch_node import DispatchNode
# from nexus.agent.nodes.responder_node import ResponderNode
# from nexus.agent.nodes.reflection_node import ReflectionNode
# from nexus.agent.nodes.reviewer_node import ReviewerNode

__all__: list[str] = []
