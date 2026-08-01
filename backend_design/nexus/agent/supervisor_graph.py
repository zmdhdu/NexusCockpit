# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Supervisor Graph — Multi-Agent 工作流编排入口

Supervisor 调度 + 5 专家并行 + Responder 汇总 + Reflection 反思 + Reviewer 审查。

图结构:
    supervisor → [条件分派] → vehicle_expert  ↘
                          → nav_expert         → responder → reflection → reviewer → END
                          → lifestyle_expert  ↗
                          → health_expert     ↗
                          → chat_expert       ↗
                          → responder (澄清/无专家时直连)

增强特性:
    - Tool→LLM 合成: 工具调用结果回传 LLM 生成自然语言回复
    - 反思校验: 对 LLM 输出做事实性/一致性/无幻觉检查
    - 自我批评: 反思不通过时自动修正回复

架构 (P0-2 拆分后):
    SupervisorGraph (编排入口, ~200行)
      ├── NodeContext (共享依赖容器)
      │     ├── intent_router / memory_manager / skill_registry
      │     ├── llm_client (AsyncOpenAI, 待 P1-1 统一移除)
      │     ├── chat_model (ChatOpenAI, call_llm_with_fallback)
      │     ├── experts (dict[str, BaseExpertAgent])
      │     ├── responder (ResponderAgent → compressor)
      │     ├── reviewer (ReviewerAgent)
      │     ├── prompt_manager (PromptManager)
      │     └── _background_tasks (set)
      │
      ├── graph_builder.py (build_supervisor_graph)
      │     └── 注册节点 + 边连接 + 编译
      │
      ├── nodes/supervisor_node.py (SupervisorNode)
      │     └── run() → 记忆召回 + 意图路由 + 专家分派决策
      │
      ├── nodes/dispatch_node.py (DispatchNode)
      │     └── run() → asyncio.gather 并行调用 + 结果合并
      │
      ├── nodes/responder_node.py (ResponderNode)
      │     └── run() → 汇总专家输出 + LLM 生成 + Tool 合成
      │     └── generate_llm_response() / stream_llm_response()
      │     └── get_system_prompt() / format_key_context() / get_location_status()
      │
      ├── nodes/reflection_node.py (ReflectionNode)
      │     └── run() → 三种反思分支 + 日期校验 + 幻觉检查
      │     └── pre_check_chat_response() / post_check_chat_response()
      │
      └── nodes/reviewer_node.py (ReviewerNode)
            └── run() → 质量检查 + 记忆存储 + 延迟统计
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from nexus.agent.experts import (
    ChatExpert,
    HealthExpert,
    LifestyleExpert,
    NavExpert,
    VehicleExpert,
)
from nexus.agent.experts.base import BaseExpertAgent
from nexus.agent.graph_builder import build_supervisor_graph
from nexus.agent.llm_client_factory import get_chat_model, get_llm_client
from nexus.agent.nodes.context import NodeContext
from nexus.agent.nodes.dispatch_node import DispatchNode
from nexus.agent.nodes.reflection_node import ReflectionNode
from nexus.agent.responder import ResponderAgent
from nexus.agent.nodes.responder_node import ResponderNode
from nexus.agent.nodes.reviewer_node import ReviewerNode
from nexus.agent.nodes.supervisor_node import SupervisorNode
from nexus.agent.reviewer import ReviewerAgent
from nexus.core.logger import get_logger
from nexus.intent.router import IntentRouterService
from nexus.memory.manager import MemoryManager
from nexus.models.state import SupervisorState
from nexus.observability.langfuse import observe
from nexus.prompts import PromptManager
from nexus.skills.registry import SkillRegistry

logger = get_logger(__name__)


class SupervisorGraph:
    """Supervisor 多智能体工作流编排器。

    使用 LangGraph StateGraph 构建 Supervisor → Experts → Responder → Reviewer 工作流。
    支持 invoke()（同步）和 stream()（流式）两种调用模式。

    P0-2 拆分后: 本类仅保留编排入口职责（初始化 + invoke/stream），
    节点逻辑已拆分到 agent/nodes/ 目录下的各节点文件中。

    Args:
        intent_router: 意图路由服务
        memory_manager: 记忆管理器
        skill_registry: 技能注册中心
        llm_client: OpenAI 兼容的 LLM 客户端（可选）
        checkpoint_saver: LangGraph checkpoint 持久化器（可选）
    """

    def __init__(
        self,
        intent_router: IntentRouterService,
        memory_manager: MemoryManager,
        skill_registry: SkillRegistry,
        llm_client: Any | None = None,
        checkpoint_saver=None,
    ):
        # LLM 客户端 — 优先使用外部注入的，否则通过工厂创建单例
        self.llm_client = llm_client or get_llm_client()

        # 初始化 5 个专家
        self.experts: dict[str, BaseExpertAgent] = {
            "vehicle": VehicleExpert(skill_registry),
            "navigation": NavExpert(skill_registry),
            "lifestyle": LifestyleExpert(skill_registry),
            "health": HealthExpert(skill_registry),
            "chat": ChatExpert(skill_registry),
        }

        # Responder 和 Reviewer
        self.responder = ResponderAgent(self.llm_client)
        self.reviewer = ReviewerAgent(memory_manager)

        # Prompt 模板管理器
        self.prompt_manager = PromptManager()

        # ChatOpenAI 实例（来自 get_chat_model，待 P1-1 统一迁移使用）
        self.chat_model = get_chat_model()

        # 构建 NodeContext 共享依赖容器
        self._ctx = NodeContext(
            intent_router=intent_router,
            memory_manager=memory_manager,
            skill_registry=skill_registry,
            llm_client=self.llm_client,
            chat_model=self.chat_model,
            experts=self.experts,
            responder=self.responder,
            reviewer=self.reviewer,
            prompt_manager=self.prompt_manager,
            checkpoint_saver=checkpoint_saver,
        )

        # 创建各节点实例（通过依赖注入获取共享服务）
        self.supervisor_node = SupervisorNode(self._ctx)
        self.dispatch_node = DispatchNode(self._ctx)
        self.responder_node = ResponderNode(self._ctx)
        self.reflection_node = ReflectionNode(self._ctx)
        self.reviewer_node = ReviewerNode(self._ctx)

        # 设置跨节点引用（避免循环依赖，在两个节点创建后注入）
        self.responder_node.set_reflection_node(self.reflection_node)
        self.reflection_node.set_responder_node(self.responder_node)

        # Checkpoint 持久化
        self.checkpoint_saver = checkpoint_saver

        # 构建 LangGraph 图
        self._graph = build_supervisor_graph(
            supervisor_run=self.supervisor_node.run,
            dispatch_run=self.dispatch_node.run,
            responder_run=self.responder_node.run,
            reflection_run=self.reflection_node.run,
            reviewer_run=self.reviewer_node.run,
            route_fn=self.supervisor_node.route,
            state_schema=SupervisorState,
            experts=self.experts,
            checkpoint_saver=checkpoint_saver,
        )

    # ---- 公共接口 ----

    @observe(name="supervisor-invoke", as_type="agent")
    async def invoke(self, state: SupervisorState) -> SupervisorState:
        """同步执行整个工作流（等待全部完成）。

        如果执行了阈值压缩，用压缩后的历史替换 state["history"]，
        确保 SessionStore 保存的是压缩后的历史而非原始历史。

        Args:
            state: SupervisorState 字典（用 create_initial_state 创建）

        Returns:
            完成后的完整 SupervisorState
        """
        config = {}
        if self.checkpoint_saver:
            thread_id = state.get("session_id") or state.get("user_id", "default")
            config = {"configurable": {"thread_id": thread_id}}
        result = await self._graph.ainvoke(state, config=config)

        # 如果执行了阈值压缩，用压缩后的历史（含新轮次）替换原始历史
        # LangGraph 的 add reducer 会将新轮次追加到原始历史，
        # 但我们希望保存的是压缩后的历史 + 新轮次
        compressed = result.pop("_compressed_history", None)
        if compressed is not None:
            result["history"] = compressed

        return result

    async def stream(self, state: SupervisorState) -> AsyncGenerator[str, None]:
        """流式执行工作流，逐块输出响应文本。

        流程:
            1. Supervisor 节点（记忆+路由+分派，不输出）
            2. 专家并行执行（不输出）
            3. Responder 流式输出 LLM 回复
            4. Reviewer 后处理（不输出）

        Args:
            state: SupervisorState 字典

        Yields:
            响应文本块
        """
        # Phase 1: Supervisor
        supervisor_update = await self.supervisor_node.run(state)
        state.update(supervisor_update)

        # Phase 2: 澄清分支
        if state.get("need_clarification") and state.get("clarification_prompt"):
            yield state["clarification_prompt"]
            state["final_response"] = state["clarification_prompt"]
            # Reviewer 后台执行，不阻塞
            try:
                task = asyncio.create_task(self.reviewer_node.run(state))
                self._ctx._background_tasks.add(task)
                task.add_done_callback(self._ctx._background_tasks.discard)
            except Exception as e:
                logger.error(f"Background reviewer task failed: {e}")
            return

        # Phase 3: 专家并行执行
        if state.get("active_experts"):
            dispatch_update = await self.dispatch_node.run(state)
            state.update(dispatch_update)

        # Phase 4: 流式响应
        full_response = ""

        if state.get("skill_handled"):
            # B1: 搜索类技能 → 先收集完整回复，做反思后统一发送
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                full_response = await self.responder_node.generate_llm_response(state)
                state["final_response"] = full_response
                # 搜索类回复也走反思校验
                reflection_update = await self.reflection_node.run(state)
                if reflection_update.get("final_response"):
                    full_response = reflection_update["final_response"]
                if reflection_update.get("metadata"):
                    state.setdefault("metadata", {}).update(reflection_update["metadata"])
                yield full_response

            # B2: 工具返回了结构化数据 → Tool→LLM 合成 + 反思
            elif state.get("tool_result") and state.get("tool_result", {}).get("data"):
                full_response = await self.responder_node.synthesize_tool_response(state)
                state["final_response"] = full_response
                reflection_update = await self.reflection_node.run(state)
                if reflection_update.get("final_response"):
                    full_response = reflection_update["final_response"]
                # 合并反思 metadata 到 state
                if reflection_update.get("metadata"):
                    state.setdefault("metadata", {}).update(reflection_update["metadata"])
                yield full_response

            # B3: 简单车控指令
            else:
                expert_results = state.get("expert_results", [])
                for er in expert_results:
                    if er.get("handled") and er.get("reply"):
                        full_response = er["reply"]
                        yield full_response
                        break

        # 分支 C: LLM 闲聊
        if not full_response:
            # 闲聊回复改为"先生成完整回复 → 渐进式反思校验 → 再发送"
            # 对所有闲聊回复都走 LLM 反思 + retry 流程，确保答案准确后再返回用户
            full_response = await self.responder_node.generate_llm_response(state)
            state["final_response"] = full_response
            # 通用闲聊反思校验（渐进式校验机制）
            reflection_update = await self.reflection_node.run(state)
            if reflection_update.get("final_response"):
                full_response = reflection_update["final_response"]
            if reflection_update.get("metadata"):
                state.setdefault("metadata", {}).update(reflection_update["metadata"])
            yield full_response

        state["final_response"] = full_response

        # 更新历史 — 如果执行了阈值压缩，使用压缩后的历史作为基础
        # 这样 SessionStore 保存的就是压缩后的历史 + 新轮次
        new_turn = [
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": full_response},
        ]
        if "_compressed_history" in state:
            state["history"] = state["_compressed_history"] + new_turn
        else:
            state.setdefault("history", []).extend(new_turn)

        # Phase 5: Reviewer 后台异步执行（不阻塞流式输出）
        try:
            task = asyncio.create_task(self.reviewer_node.run(state))
            self._ctx._background_tasks.add(task)
            task.add_done_callback(self._ctx._background_tasks.discard)
        except Exception as e:
            logger.error(f"Background reviewer task failed: {e}")

    @observe(name="supervisor-stream-with-events")
    async def stream_with_events(self, state: SupervisorState) -> AsyncGenerator[dict, None]:
        """流式执行工作流，输出结构化事件。

        性能优化:
            - 启发式路由优先，常见车控指令 <1ms 命中
            - Reviewer 后台异步执行，不阻塞 done 事件
            - 用户感知延迟大幅降低

        事件类型:
            - {"type": "thinking", "data": {"message": "正在思考..."}}
            - {"type": "intent", "data": {"intent": "...", "source": "..."}}
            - {"type": "experts", "data": {"experts": ["vehicle", "chat"]}}
            - {"type": "action", "data": {"action": "vehicle_climate"}}
            - {"type": "chunk", "data": {"chunk": "..."}}
            - {"type": "done", "data": {"response": "...", "latency_ms": ...}}

        Args:
            state: SupervisorState 字典

        Yields:
            事件字典
        """
        # 立即发送 thinking 事件，让前端尽早显示加载状态
        yield {"type": "thinking", "data": {"message": "正在思考..."}}

        # Phase 1: Supervisor（记忆+路由并行，已优化）
        supervisor_update = await self.supervisor_node.run(state)
        state.update(supervisor_update)

        # 发送意图事件
        intent_name = state.get("intent_source", "")
        yield {"type": "intent", "data": {"intent": intent_name, "source": intent_name}}

        # Phase 2: 澄清分支
        if state.get("need_clarification") and state.get("clarification_prompt"):
            yield {"type": "chunk", "data": {"chunk": state["clarification_prompt"]}}
            state["final_response"] = state["clarification_prompt"]
            # Reviewer 后台执行，不阻塞 done 事件
            _task = asyncio.create_task(self.reviewer_node.run(state))
            self._ctx._background_tasks.add(_task)
            _task.add_done_callback(self._ctx._background_tasks.discard)
            yield {
                "type": "done",
                "data": {
                    "response": state["final_response"],
                    "latency_ms": state.get("latency_ms", 0),
                },
            }
            return

        # Phase 3: 专家并行执行
        if state.get("active_experts"):
            yield {"type": "experts", "data": {"experts": state["active_experts"]}}
            dispatch_update = await self.dispatch_node.run(state)
            state.update(dispatch_update)
            if state.get("skill_action"):
                yield {"type": "action", "data": {"action": state["skill_action"]}}

        # Phase 4: 流式响应
        full_response = ""

        if state.get("skill_handled"):
            # B1: 搜索类技能 → 先收集完整回复，做反思后统一发送
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                yield {"type": "thinking", "data": {"message": "正在分析搜索结果..."}}
                # 先生成完整回复（不流式）
                full_response = await self.responder_node.generate_llm_response(state)
                state["final_response"] = full_response
                # 搜索类回复也走反思校验
                reflection_update = await self.reflection_node.run(state)
                if reflection_update.get("final_response"):
                    full_response = reflection_update["final_response"]
                # 合并反思 metadata 到 state
                if reflection_update.get("metadata"):
                    state.setdefault("metadata", {}).update(reflection_update["metadata"])
                yield {"type": "chunk", "data": {"chunk": full_response}}

            # B2: 工具返回了结构化数据 → Tool→LLM 合成 + 反思
            elif state.get("tool_result") and state.get("tool_result", {}).get("data"):
                yield {"type": "thinking", "data": {"message": "正在分析工具结果..."}}
                full_response = await self.responder_node.synthesize_tool_response(state)
                state["final_response"] = full_response
                reflection_update = await self.reflection_node.run(state)
                if reflection_update.get("final_response"):
                    full_response = reflection_update["final_response"]
                # 合并反思 metadata 到 state
                if reflection_update.get("metadata"):
                    state.setdefault("metadata", {}).update(reflection_update["metadata"])
                yield {"type": "chunk", "data": {"chunk": full_response}}

            # B3: 简单车控指令
            else:
                expert_results = state.get("expert_results", [])
                for er in expert_results:
                    if er.get("handled") and er.get("reply"):
                        full_response = er["reply"]
                        yield {"type": "chunk", "data": {"chunk": full_response}}
                        break

        if not full_response:
            # 闲聊回复改为"先生成完整回复 → 渐进式反思校验 → 再发送"
            # 对所有闲聊回复都走 LLM 反思 + retry 流程，确保答案准确后再返回用户
            yield {"type": "thinking", "data": {"message": "正在生成回复..."}}
            full_response = await self.responder_node.generate_llm_response(state)
            state["final_response"] = full_response
            # 通用闲聊反思校验（渐进式校验机制）
            yield {"type": "thinking", "data": {"message": "正在校验回复质量..."}}
            reflection_update = await self.reflection_node.run(state)
            if reflection_update.get("final_response"):
                full_response = reflection_update["final_response"]
            if reflection_update.get("metadata"):
                state.setdefault("metadata", {}).update(reflection_update["metadata"])
            yield {"type": "chunk", "data": {"chunk": full_response}}

        state["final_response"] = full_response
        # 更新历史 — 如果执行了阈值压缩，使用压缩后的历史作为基础
        new_turn = [
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": full_response},
        ]
        if "_compressed_history" in state:
            state["history"] = state["_compressed_history"] + new_turn
        else:
            state.setdefault("history", []).extend(new_turn)

        # Phase 5: 立即发送 done 事件（不等 Reviewer）
        # 计算已有延迟（supervisor + dispatch）
        metadata = state.get("metadata", {})
        total_latency = sum(
            metadata.get(k, 0)
            for k in metadata
            if k.endswith("_latency_ms")
        )
        state["latency_ms"] = round(total_latency, 2)

        yield {
            "type": "done",
            "data": {
                "response": state["final_response"],
                "latency_ms": state.get("latency_ms", 0),
                "intent": intent_name,
                "action": state.get("skill_action", ""),
            },
        }

        # Phase 6: Reviewer 后台异步执行（记忆存储/向量化，不阻塞用户）
        # 使用 create_task 确保在后台运行，不影响已发送的 done 事件
        try:
            _task = asyncio.create_task(self.reviewer_node.run(state))
            self._ctx._background_tasks.add(_task)
            _task.add_done_callback(self._ctx._background_tasks.discard)
        except Exception as e:
            logger.error(f"Background reviewer task failed: {e}")
