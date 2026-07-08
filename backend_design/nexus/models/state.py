"""
Supervisor State — v2.0 Multi-Agent 共享状态定义

v2.0 变更:
  - 从 @dataclass 改为 TypedDict（LangGraph 原生支持）
  - 增加 Annotated reducer：list 用 add 累加，dict 用 merge_dict 合并
  - 新增 expert_results / active_experts / query_type 等字段
  - history 用 add 累加，避免节点间覆盖

reducer 说明:
  - Annotated[list, add]:       多节点并行写入时列表自动拼接
  - Annotated[dict, merge_dict]: 多节点并行写入时字典自动合并
  - 无 Annotated 的字段:        最后一个写入者覆盖（last writer wins）
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, Dict, List, TypedDict


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
    """v2.0 Supervisor 多智能体工作流共享状态。

    所有节点（Supervisor / 5个专家 / Responder / Reviewer）
    读写同一个 SupervisorState 字典，通过 reducer 机制自动合并。

    字段分组:
        - 输入: user_input, user_id, session_id
        - 记忆: recalled_memories, memory_str, user_profile
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

    # ---- 记忆召回 ----
    recalled_memories: Annotated[List[str], add]
    memory_str: str
    user_profile: Dict[str, Any]

    # ---- 意图路由 / Supervisor 分派 ----
    intent: Dict[str, Any]
    intent_source: str
    need_clarification: bool
    clarification_prompt: str
    active_experts: List[str]           # Supervisor 决定分派给哪些专家
    query_type: str                     # memory / knowledge / hybrid

    # ---- 专家输出（并行累加） ----
    expert_results: Annotated[List[Dict[str, Any]], add]

    # ---- 兼容 v1.0 技能字段 ----
    skill_result: Any                   # DispatchResult
    skill_handled: bool
    skill_action: str
    search_context: str
    # 副作用标记: 车控等操作会修改车辆状态，此类响应禁止写入语义缓存
    # 避免 "打开空调" 缓存命中后车控指令不执行的安全事故 (from main L5 fix)
    has_side_effect: bool

    # ---- LLM 对话 ----
    history: Annotated[List[Dict[str, str]], add]
    running_summary: str
    llm_response: str

    # ---- 最终输出 ----
    final_response: str
    metadata: Annotated[Dict[str, Any], merge_dict]

    # ---- 可观测性 ----
    trace_id: str
    span_ids: Annotated[Dict[str, str], merge_dict]
    latency_ms: float


# ---- v1.0 向后兼容 ----
# chat.py 等旧代码用 AgentState(user_input=..., ...) 构造，
# v2.0 改为直接用 dict，但保留别名避免大规模改键

AgentState = SupervisorState


def create_initial_state(
    user_input: str,
    user_id: str = "default",
    session_id: str = "",
    history: List[Dict[str, str]] | None = None,
) -> SupervisorState:
    """创建初始 SupervisorState（v2.0 推荐入口）。

    替代 v1.0 的 AgentState(user_input=..., ...) 构造方式，
    确保所有带 reducer 的字段都有正确的初始值。

    Args:
        user_input: 用户输入文本
        user_id: 用户 ID
        session_id: 会话 ID
        history: 历史对话（从 checkpoint 或内存恢复）

    Returns:
        初始化好的 SupervisorState 字典
    """
    return SupervisorState(
        user_input=user_input,
        user_id=user_id,
        session_id=session_id,
        recalled_memories=[],
        memory_str="",
        user_profile={},
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
        has_side_effect=False,
        history=list(history) if history else [],
        running_summary="",
        llm_response="",
        final_response="",
        metadata={},
        trace_id="",
        span_ids={},
        latency_ms=0.0,
    )
