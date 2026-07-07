"""
Agent State — Multi-Agent 共享状态定义

本文件定义了 LangGraph 工作流中各 Agent 之间传递的共享状态。
所有 Agent (Planner/Executor/Responder/Reviewer) 都读写同一个 AgentState 对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentState:
    """LangGraph 工作流共享状态。

    这个对象贯穿整个 Multi-Agent 管道，每个 Agent 读取前一阶段的结果
    并写入自己的输出，供下一阶段使用。

    字段分组:
        - 输入: user_input, user_id, session_id
        - 记忆: recalled_memories, memory_str (Planner 写入)
        - 意图: intent, intent_source, need_clarification (Planner 写入)
        - 技能: skill_result, skill_handled, skill_action (Executor 写入)
        - 对话: history, running_summary (Responder 读写)
        - 输出: final_response, metadata (Responder/Reviewer 写入)
        - 可观测: trace_id, span_ids, latency_ms (各阶段写入)
    """

    # 输入
    user_input: str = ""
    user_id: str = "default"
    session_id: str = ""

    # 记忆召回
    recalled_memories: List[str] = field(default_factory=list)
    memory_str: str = ""

    # 意图路由
    intent: Dict[str, Any] = field(default_factory=dict)
    intent_source: str = ""
    need_clarification: bool = False
    clarification_prompt: str = ""

    # 技能执行
    skill_result: Any = None  # DispatchResult
    skill_handled: bool = False
    skill_action: str = ""
    search_context: str = ""

    # LLM 对话
    history: List[Dict[str, str]] = field(default_factory=list)
    running_summary: str = ""
    llm_response: str = ""

    # 最终输出
    final_response: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 可观测性
    trace_id: str = ""
    span_ids: Dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0
