# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Supervisor State — Multi-Agent 共享状态定义

核心特性:
  - 使用 TypedDict（LangGraph 原生支持）
  - 增加 Annotated reducer：list 用 add 累加，dict 用 merge_dict 合并
  - 包含 expert_results / active_experts / query_type 等字段
  - history 用 add 累加，避免节点间覆盖

reducer 说明:
  - Annotated[list, add]:       多节点并行写入时列表自动拼接
  - Annotated[dict, merge_dict]: 多节点并行写入时字典自动合并
  - 无 Annotated 的字段:        最后一个写入者覆盖（last writer wins）
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict


def merge_dict(left: dict, right: dict) -> dict:
    """字典合并 reducer：right 优先覆盖 left。

    用于 metadata / span_ids 等多节点并行写入的字典字段，
    确保并行专家不会互相覆盖而是合并各自的输出。
    """
    result = dict(left or {})
    if right:
        result.update(right)
    return result


class SupervisorState(TypedDict, total=False):
    """Supervisor 多智能体工作流共享状态。

    所有节点（Supervisor / 5个专家 / Responder / Reviewer）
    读写同一个 SupervisorState 字典，通过 reducer 机制自动合并。

    关键字段:
        - key_context: 从短期对话历史提取的关键上下文（位置/偏好/身份）
        - _compressed_history: 阈值压缩后的历史（内部使用，不持久化）

    字段分组:
        - 输入: user_input, user_id, session_id
        - 记忆: recalled_memories, memory_str, user_profile, key_context
        - Supervisor 路由: intent, intent_source, need_clarification,
          active_experts, query_type
        - 专家输出: expert_results (累加), search_context
        - 对话: history (累加), running_summary, llm_response
        - 输出: final_response, metadata (合并)
        - 可观测: trace_id, span_ids (合并), latency_ms
    """
    # ---- 输入 ----
    user_input: str
    user_id: str
    session_id: str
    cockpit_id: str  # 座舱 ID（多租户隔离键）

    # ---- 记忆召回 ----
    recalled_memories: Annotated[list[str], add]
    memory_str: str
    habits_str: str  # 用户习惯（从 MySQL 加载）
    user_profile: dict[str, Any]
    key_context: dict[str, Any]  # 从短期历史提取的关键上下文（位置/偏好/身份）

    # ---- 意图路由 / Supervisor 分派 ----
    intent: dict[str, Any]
    intent_source: str
    need_clarification: bool
    clarification_prompt: str
    active_experts: list[str]           # Supervisor 决定分派给哪些专家
    query_type: str                     # memory / knowledge / hybrid

    # ---- 专家输出（并行累加） ----
    expert_results: Annotated[list[dict[str, Any]], add]

    # ---- 技能字段 ----
    skill_result: Any                   # DispatchResult
    skill_handled: bool
    skill_action: str
    search_context: str
    # 工具调用结果（供 Responder 做 LLM 合成和反思校验）
    tool_result: dict[str, Any]         # {tool_name, message, data, handled}
    # 副作用标记: 车控等操作会修改车辆状态，此类响应禁止写入语义缓存
    # 避免 "打开空调" 缓存命中后车控指令不执行的安全事故 (from main L5 fix)
    has_side_effect: bool

    # ---- LLM 对话 ----
    history: Annotated[list[dict[str, str]], add]
    running_summary: str
    llm_response: str
    _compressed_history: list[dict[str, str]]  # 阈值压缩后的历史（内部传递用）

    # ---- 最终输出 ----
    final_response: str
    metadata: Annotated[dict[str, Any], merge_dict]

    # ---- 可观测性 ----
    trace_id: str
    span_ids: Annotated[dict[str, str], merge_dict]
    latency_ms: float


# ---- 向后兼容 ----
# chat.py 等旧代码用 AgentState(user_input=..., ...) 构造，
# 改为直接用 dict，但保留别名避免大规模改键

AgentState = SupervisorState


def create_initial_state(
    user_input: str,
    user_id: str = "default",
    session_id: str = "",
    history: list[dict[str, str]] | None = None,
    running_summary: str = "",
) -> SupervisorState:
    """创建初始 SupervisorState（推荐入口）。

    确保所有带 reducer 的字段都有正确的初始值。

    特性:
        - 支持 running_summary 参数，从 SessionStore 加载滚动摘要
        - 初始化 key_context 为空字典

    Args:
        user_input: 用户输入文本
        user_id: 用户 ID
        session_id: 会话 ID
        history: 历史对话（从 checkpoint 或内存恢复）
        running_summary: 滚动摘要（从 SessionStore 加载）

    Returns:
        初始化好的 SupervisorState 字典
    """
    return SupervisorState(
        user_input=user_input,
        user_id=user_id,
        session_id=session_id,
        cockpit_id="cockpit-01",  # 默认座舱
        recalled_memories=[],
        memory_str="",
        habits_str="",  # 用户习惯
        user_profile={},
        key_context={},  # 关键上下文
        intent={},
        intent_source="",
        need_clarification=False,
        clarification_prompt="",
        active_experts=[],
        query_type="",
        expert_results=[],
        skill_result=None,
        skill_handled=False,
        skill_action="",
        search_context="",
        tool_result={},  # 工具调用结果
        has_side_effect=False,
        history=list(history) if history else [],
        running_summary=running_summary,  # 从 SessionStore 加载的滚动摘要
        llm_response="",
        final_response="",
        metadata={},
        trace_id="",
        span_ids={},
        latency_ms=0.0,
    )
