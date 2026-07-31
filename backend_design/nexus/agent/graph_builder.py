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

框架组件集成 (langgraph-prebuilt 1.0.6 已安装):
  - create_tool_node(): 从 SkillRegistry 创建 langgraph.prebuilt.ToolNode
  - build_graph_with_reflection_loop(): 用条件边实现 "反思→修正→再检查" 循环
  - build_graph_with_parallel_experts(): 用 LangGraph 原生并行节点替代 asyncio.gather
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
    checkpoint_saver: Any = None,
):
    """构建 Supervisor → Experts → Responder → Reflection → Reviewer 工作流。

    图结构:
        supervisor → [条件分派] → dispatch → responder → reflection → reviewer → END
                          ↓
                     responder (澄清/无专家时直连)

    Args:
        supervisor_run: Supervisor 节点可调用对象
        dispatch_run: Dispatch 节点可调用对象
        responder_run: Responder 节点可调用对象
        reflection_run: Reflection 节点可调用对象
        reviewer_run: Reviewer 节点可调用对象
        route_fn: Supervisor 条件路由函数
        state_schema: LangGraph 状态类型 (SupervisorState)
        checkpoint_saver: 可选的 checkpoint 持久化器

    Returns:
        编译后的 LangGraph CompiledGraph
    """
    workflow = StateGraph(state_schema)

    # ---- 注册节点 ----
    workflow.add_node("supervisor", supervisor_run)
    workflow.add_node("dispatch", dispatch_run)
    workflow.add_node("responder", responder_run)
    workflow.add_node("reflection", reflection_run)
    workflow.add_node("reviewer", reviewer_run)

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


# ============================================================
# 框架组件集成: ToolNode / 反思条件边 / 并行节点
# ============================================================

def create_tool_node(skill_registry: Any):
    """从 SkillRegistry 创建 langgraph.prebuilt.ToolNode。

    Phase 4.3 #2 改进: 使用 langgraph.prebuilt.ToolNode 替代手写工具合成。

    ToolNode 自动处理:
      - OpenAI function calling 格式的 tool_calls
      - 工具执行 + 结果格式化为 ToolMessage
      - 与 create_react_agent 集成

    用法:
        tools = skill_registry.get_langchain_tools()
        tool_node = create_tool_node(skill_registry)
        # 在图中注册 tool_node 节点

    Args:
        skill_registry: SkillRegistry 实例

    Returns:
        langgraph.prebuilt.ToolNode 实例，或 None（如果 langgraph-prebuilt 未安装）
    """
    try:
        from langgraph.prebuilt import ToolNode
    except ImportError:
        logger.warning("langgraph-prebuilt not installed, ToolNode creation skipped")
        return None

    tools = skill_registry.get_langchain_tools()
    if not tools:
        logger.warning("No LangChain tools available from SkillRegistry, ToolNode not created")
        return None

    tool_node = ToolNode(tools)
    logger.info(f"ToolNode created with {len(tools)} tools from SkillRegistry")
    return tool_node


def build_graph_with_reflection_loop(
    supervisor_run: Any,
    dispatch_run: Any,
    responder_run: Any,
    reflection_run: Any,
    reviewer_run: Any,
    route_fn: Any,
    reflection_route_fn: Any,
    state_schema: type,
    checkpoint_saver: Any = None,
    max_reflection_retries: int = 1,
):
    """构建带反思条件边循环的工作流。

    Phase 4.3 #3 改进: 用 LangGraph 条件边实现 "反思→修正→再检查" 循环。

    图结构:
        supervisor → [条件分派] → dispatch → responder → reflection → [条件路由]
                          ↓                                      ├→ reviewer → END (通过)
                     responder (澄清)                            └→ responder (不通过, retry)

    与 build_supervisor_graph() 的区别:
      - reflection 后不再直连 reviewer，而是通过条件边判断
      - 反思通过 → reviewer → END
      - 反思不通过且有修正建议 → responder (重新生成)
      - 最多重试 max_reflection_retries 次，防止无限循环

    Args:
        reflection_route_fn: 反思条件路由函数，返回 "pass" 或 "retry"
        max_reflection_retries: 最大反思重试次数

    Returns:
        编译后的 LangGraph CompiledGraph
    """
    workflow = StateGraph(state_schema)

    # ---- 注册节点 ----
    workflow.add_node("supervisor", supervisor_run)
    workflow.add_node("dispatch", dispatch_run)
    workflow.add_node("responder", responder_run)
    workflow.add_node("reflection", reflection_run)
    workflow.add_node("reviewer", reviewer_run)

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

    # ---- dispatch → responder → reflection ----
    workflow.add_edge("dispatch", "responder")
    workflow.add_edge("responder", "reflection")

    # ---- 条件边: reflection → reviewer (通过) 或 responder (重试) ----
    # 替代原来的 workflow.add_edge("reflection", "reviewer")
    workflow.add_conditional_edges(
        "reflection",
        reflection_route_fn,
        {
            "pass": "reviewer",    # 反思通过 → 进入 reviewer
            "retry": "responder",  # 反思不通过 → 重新生成回复
        },
    )

    # ---- reviewer → END ----
    workflow.add_edge("reviewer", END)

    # ---- 编译图 ----
    compile_kwargs: dict[str, Any] = {}
    if checkpoint_saver:
        compile_kwargs["checkpointer"] = checkpoint_saver

    compiled = workflow.compile(**compile_kwargs)
    logger.info(
        f"Supervisor graph built with reflection loop: "
        f"supervisor → dispatch → responder → reflection → [pass→reviewer | retry→responder] → END "
        f"(max_retries={max_reflection_retries})"
    )
    return compiled


def build_graph_with_parallel_experts(
    supervisor_run: Any,
    expert_runs: dict[str, Any],
    responder_run: Any,
    reflection_run: Any,
    reviewer_run: Any,
    route_fn: Any,
    state_schema: type,
    checkpoint_saver: Any = None,
):
    """构建使用 LangGraph 原生并行节点的工作流。

    Phase 4.3 #4 改进: 用 LangGraph 原生并行节点替代手写 asyncio.gather 分派。

    图结构:
        supervisor → [条件分派] → vehicle_expert  ↘
                          → nav_expert         → responder → reflection → reviewer → END
                          → lifestyle_expert  ↗
                          → health_expert     ↗
                          → chat_expert       ↗
                          → responder (澄清/无专家时直连)

    与 build_supervisor_graph() 的区别:
      - 每个专家注册为独立的图节点
      - LangGraph 自动并行执行通过 add_edge 从同一节点连出的多条边
      - 无需手写 asyncio.gather，框架自动处理并行 + 结果合并
      - expert_results 通过 Annotated[list, add] reducer 自动累加

    Args:
        expert_runs: 专家名称到可调用对象的映射，如 {"vehicle": vehicle_run, "nav": nav_run}
        route_fn: Supervisor 条件路由函数，返回专家名称列表

    Returns:
        编译后的 LangGraph CompiledGraph
    """
    workflow = StateGraph(state_schema)

    # ---- 注册节点 ----
    workflow.add_node("supervisor", supervisor_run)
    workflow.add_node("responder", responder_run)
    workflow.add_node("reflection", reflection_run)
    workflow.add_node("reviewer", reviewer_run)

    # 注册每个专家为独立节点
    for expert_name, expert_run in expert_runs.items():
        workflow.add_node(f"expert_{expert_name}", expert_run)
        logger.debug(f"Registered expert node: expert_{expert_name}")

    # ---- 入口 ----
    workflow.set_entry_point("supervisor")

    # ---- 条件边: Supervisor → 各专家节点 或 responder ----
    # route_fn 返回活跃专家名称列表，LangGraph 自动并行执行
    expert_route_map = {name: f"expert_{name}" for name in expert_runs}
    expert_route_map["responder"] = "responder"  # 澄清/无专家时直连
    workflow.add_conditional_edges(
        "supervisor",
        route_fn,
        expert_route_map,
    )

    # ---- 所有专家 → responder → reflection → reviewer → END ----
    for expert_name in expert_runs:
        workflow.add_edge(f"expert_{expert_name}", "responder")

    workflow.add_edge("responder", "reflection")
    workflow.add_edge("reflection", "reviewer")
    workflow.add_edge("reviewer", END)

    # ---- 编译图 ----
    compile_kwargs: dict[str, Any] = {}
    if checkpoint_saver:
        compile_kwargs["checkpointer"] = checkpoint_saver

    compiled = workflow.compile(**compile_kwargs)
    logger.info(
        f"Supervisor graph built with parallel experts: "
        f"supervisor → [{', '.join(expert_runs.keys())}] (parallel) → responder → reflection → reviewer → END"
    )
    return compiled
