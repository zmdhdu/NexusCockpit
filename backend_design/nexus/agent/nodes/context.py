# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
NodeContext — 节点共享上下文

封装各节点需要的共享依赖（LLM 客户端、记忆管理器等），
避免每个节点独立初始化，统一由 SupervisorGraph 注入。

未来改进标记:
  - LangGraph StateGraph 本身通过 state dict 传递上下文，
    NodeContext 可进一步迁移为 state 中的不可变字段
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from typing import Any

from nexus.agent.responder import ResponderAgent
from nexus.agent.reviewer import ReviewerAgent
from nexus.intent.router import IntentRouterService
from nexus.memory.manager import MemoryManager
from nexus.prompts import PromptManager
from nexus.skills.registry import SkillRegistry


@dataclass
class NodeContext:
    """节点共享上下文 — 由 SupervisorGraph 创建并注入各节点。

    Attributes:
        llm_client: 统一 LLM 客户端（来自工厂单例）
        intent_router: 意图路由服务
        memory_manager: 记忆管理器
        skill_registry: 技能注册中心
        responder: 响应生成 Agent
        reviewer: 质量审查 Agent
        prompt_manager: Prompt 模板管理器
        experts: 专家 Agent 字典
    """

    llm_client: Any
    intent_router: IntentRouterService
    memory_manager: MemoryManager
    skill_registry: SkillRegistry
    responder: ResponderAgent
    reviewer: ReviewerAgent
    prompt_manager: PromptManager
    experts: dict[str, Any]
