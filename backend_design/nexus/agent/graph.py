# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Agent Graph — LangGraph Multi-Agent 工作流编排

本模块是整个 Agent 系统的"指挥中心"，使用 LangGraph 库构建有向图工作流。

工作流程:
    用户输入 → Planner(规划) → Executor(执行) → Responder(响应) → Reviewer(审查) → 输出

特殊路由:
    当 Planner 判断需要澄清时，跳过 Executor 直接进入 Responder

四个 Agent 的职责:
    - Planner:   召回记忆 + 路由意图 + 判断是否需要澄清
    - Executor:  根据意图调度技能 (空调/车窗/导航/搜索等)
    - Responder: 生成最终用户回复 (技能回复 / LLM 闲聊)
    - Reviewer:  质量检查 + 触发记忆存储 + 计算延迟
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from langgraph.graph import END, StateGraph

from nexus.agent.executor import ExecutorAgent
from nexus.agent.planner import PlannerAgent
from nexus.agent.responder import ResponderAgent
from nexus.agent.reviewer import ReviewerAgent
from nexus.core.logger import get_logger
from nexus.intent.router import IntentRouterService
from nexus.memory.manager import MemoryManager
from nexus.models.state import AgentState
from nexus.skills.orchestrator import SkillOrchestrator
from nexus.skills.registry import SkillRegistry

logger = get_logger(__name__)


class AgentGraph:
    """Multi-Agent 工作流编排器。

    使用 LangGraph 构建 Planner → Executor → Responder → Reviewer 管道。
    支持同步调用 (invoke) 和流式调用 (stream) 两种模式。

    Args:
        intent_router: 意图路由服务，判断用户意图
        memory_manager: 记忆管理器，负责记忆召回与存储
        skill_registry: 技能注册中心，管理所有可用技能
        llm_client: OpenAI 兼容的 LLM 客户端 (可选)
    """

    def __init__(
        self,
        intent_router: IntentRouterService,
        memory_manager: MemoryManager,
        skill_registry: SkillRegistry,
        llm_client=None,
    ):
        self.planner = PlannerAgent(intent_router, memory_manager)
        self.executor = ExecutorAgent(SkillOrchestrator(skill_registry))
        self.responder = ResponderAgent(llm_client)
        self.reviewer = ReviewerAgent(memory_manager)
        self._graph = self._build_graph()

    def _build_graph(self):
        """构建 LangGraph 有向图工作流。

        图结构:
            planner → [条件] → executor → responder → reviewer → END
                        ↘ responder (需要澄清时)

        Returns:
            编译后的 LangGraph 可执行图
        """
        workflow = StateGraph(AgentState)

        # 注册节点
        workflow.add_node("planner", self.planner.plan)
        workflow.add_node("executor", self.executor.execute)
        workflow.add_node("responder", self.responder.respond)
        workflow.add_node("reviewer", self.reviewer.review)

        # 设置入口
        workflow.set_entry_point("planner")

        # 条件边: planner → executor (正常) / planner → responder (需要澄清)
        workflow.add_conditional_edges(
            "planner",
            lambda state: "responder" if state.need_clarification else "executor",
            {"executor": "executor", "responder": "responder"},
        )

        # 正常边: executor → responder → reviewer → END
        workflow.add_edge("executor", "responder")
        workflow.add_edge("responder", "reviewer")
        workflow.add_edge("reviewer", END)

        return workflow.compile()

    async def invoke(self, state: AgentState) -> AgentState:
        """同步执行整个工作流 (等待全部完成)。

        Args:
            state: 包含用户输入、历史等信息的 Agent 状态

        Returns:
            更新后的 Agent 状态 (包含最终响应)
        """
        result = await self._graph.ainvoke(state)
        return result

    async def stream(self, state: AgentState) -> AsyncGenerator[str, None]:
        """流式执行工作流，逐块输出响应文本。

        适用于 SSE / WebSocket 场景，用户能看到文字逐块出现。

        流程:
            1. Planner 规划 (不输出)
            2. 如需澄清 → 输出澄清提示
            3. Executor 执行技能 (不输出)
            4. Responder 流式输出 LLM 回复
            5. Reviewer 后处理 (不输出)

        Args:
            state: Agent 状态

        Yields:
            响应文本块
        """
        # Phase 1: 规划
        state = await self.planner.plan(state)

        # Phase 2: 澄清分支
        if state.need_clarification and state.clarification_prompt:
            yield state.clarification_prompt
            state.final_response = state.clarification_prompt
            await self.reviewer.review(state)
            return

        # Phase 3: 执行技能
        state = await self.executor.execute(state)

        # Phase 4: 流式响应
        async for chunk in self.responder.stream_respond(state):
            yield chunk

        # Phase 5: 审查后处理
        await self.reviewer.review(state)
