# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
NodeContext — 节点共享依赖容器

从 SupervisorGraph.__init__() 中抽取的全部共享依赖，
通过依赖注入传递给各个节点，消除节点对 SupervisorGraph 的直接引用。

设计原则:
    - 节点间通过 NodeContext 传递依赖，无直接引用
    - 节点不持有 SupervisorGraph 引用（消除循环依赖）
    - 后台任务强引用集合统一管理，防止 asyncio.Task 被 GC 回收
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.agent.experts.base import BaseExpertAgent
from nexus.agent.responder import ResponderAgent
from nexus.agent.reviewer import ReviewerAgent
from nexus.intent.router import IntentRouterService
from nexus.memory.manager import MemoryManager
from nexus.prompts import PromptManager
from nexus.skills.registry import SkillRegistry


@dataclass
class NodeContext:
    """节点共享依赖容器。

    持有全部 Supervisor 工作流所需的服务实例，
    通过依赖注入传递给各节点（SupervisorNode / DispatchNode / ResponderNode /
    ReflectionNode / ReviewerNode）。

    Attributes:
        intent_router: 意图路由服务
        memory_manager: 记忆管理器
        skill_registry: 技能注册中心
        llm_client: AsyncOpenAI 客户端（已迁移到 chat_model.ainvoke，仅保留向后兼容）
        chat_model: ChatOpenAI 实例（来自 call_llm_with_fallback）
        experts: 专家字典 {name: BaseExpertAgent}
        responder: ResponderAgent 实例（持有 compressor）
        reviewer: ReviewerAgent 实例
        prompt_manager: Prompt 模板管理器
        checkpoint_saver: LangGraph checkpoint 持久化器
        _background_tasks: 后台任务强引用集合（防止 asyncio.Task 被 GC 回收）
    """

    intent_router: IntentRouterService
    memory_manager: MemoryManager
    skill_registry: SkillRegistry
    llm_client: Any  # AsyncOpenAI，仅 compressor/manager 向后兼容使用
    chat_model: Any  # ChatOpenAI，各节点统一调用入口
    experts: dict[str, BaseExpertAgent]
    responder: ResponderAgent
    reviewer: ReviewerAgent
    prompt_manager: PromptManager
    checkpoint_saver: Any = None
    _background_tasks: set = field(default_factory=set)
