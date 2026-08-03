# Copyright (c) 2026 zmdhdu (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Graph Builder — LangGraph 图构建器

从 SupervisorGraph._build_graph() 方法抽取，负责:
  - 节点注册 (add_node)
  - 边连接 (add_edge / add_conditional_edges)
  - 入口设置 (set_entry_point)
  - 图编译 (compile)

将图构建逻辑与节点业务逻辑分离，SupervisorGraph 瘦身为编排入口。

图结构:
    supervisor → [条件分派] → dispatch → responder → reflection → reviewer → END
                          ↓
                     responder (澄清/无专家时直连)

注意:
  - 专家节点 (vehicle_expert 等) 虽注册到图中，但实际并行调用
    由 DispatchNode.run() 内部 asyncio.gather 完成，不通过图边触发。
  - build_graph_with_reflection_loop() 和 build_graph_with_parallel_experts()
    已于 v2.2 清理删除（从未被生产代码调用，属调试占位代码）。
  - create_tool_node() 已于 v2.2 清理删除（SupervisorGraph 使用手写 _dispatch_node）。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from nexus.core.logger import get_logger

logger = get_logger(__name__)


def build_supervisor_graph(
    supervisor_run: Any,
    dispatch_run: Any,
    responder_run: Any,
    reflection_run: Any,
    reviewer_run: Any,
    route_fn: Any,
    state_schema: type,
    experts: dict[str, Any] | None = None,
    checkpoint_saver: Any = None,
):
    """构建五层链路 StateGraph。

    作用：注册核心节点 + 专家节点 + 条件路由边 + 持久化，编译为 CompiledGraph；
    场景：SupervisorGraph 初始化时调用，专家节点注册但不通过边触发（由 DispatchNode 并行调用）。

    Args:
        supervisor_run: Supervisor 节点可调用对象
        dispatch_run: Dispatch 节点可调用对象
        responder_run: Responder 节点可调用对象
        reflection_run: Reflection 节点可调用对象
        reviewer_run: Reviewer 节点可调用对象
        route_fn: Supervisor 条件路由函数
        state_schema: LangGraph 状态类型 (SupervisorState)
        experts: 专家字典 {name: BaseExpertAgent}（可选，注册到图中但不通过边触发）
        checkpoint_saver: 可选的 checkpoint 持久化器

    Returns:
        编译后的 LangGraph CompiledGraph
    """
    workflow = StateGraph(state_schema)

    # ---- 注册核心节点 ----
    workflow.add_node("supervisor", supervisor_run)
    workflow.add_node("dispatch", dispatch_run)
    workflow.add_node("responder", responder_run)
    workflow.add_node("reflection", reflection_run)
    workflow.add_node("reviewer", reviewer_run)

    # ---- 注册专家节点（注册到图中，实际并行调用由 DispatchNode 内部 asyncio.gather 完成）----
    if experts:
        expert_node_map = {
            "vehicle": "vehicle_expert",
            "navigation": "nav_expert",
            "lifestyle": "lifestyle_expert",
            "health": "health_expert",
            "chat": "chat_expert",
        }
        for expert_key, node_name in expert_node_map.items():
            expert = experts.get(expert_key)
            if expert is not None:
                workflow.add_node(node_name, expert.run)

    # ---- 入口 ----
    workflow.set_entry_point("supervisor")

    # ---- 条件边: Supervisor → dispatch 或 responder ----
    workflow.add_conditional_edges(
        "supervisor",
        route_fn,
        {
            "dispatch": "dispatch",
            "responder": "responder",
        },
    )

    # ---- dispatch → responder → reflection → reviewer → END ----
    workflow.add_edge("dispatch", "responder")
    workflow.add_edge("responder", "reflection")
    workflow.add_edge("reflection", "reviewer")
    workflow.add_edge("reviewer", END)

    # ---- 编译图 ----
    compile_kwargs: dict[str, Any] = {}
    if checkpoint_saver:
        compile_kwargs["checkpointer"] = checkpoint_saver

    compiled = workflow.compile(**compile_kwargs)
    logger.info("Supervisor graph built: supervisor → dispatch → responder → reflection → reviewer → END")
    return compiled
