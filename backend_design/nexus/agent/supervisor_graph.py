# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Supervisor Graph — Multi-Agent 工作流编排入口

作用：编排 Supervisor 调度 + 5 专家并行 + Responder 汇总 + Reflection 反思 + Reviewer 审查全链路；
场景：车载语音交互的统一工作流入口，支持同步调用与流式输出两种模式。

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

架构:
    SupervisorGraph (编排入口, ~280行)
      ├── NodeContext (共享依赖容器)
      │     ├── intent_router / memory_manager / skill_registry
      │     ├── llm_client (AsyncOpenAI, 仅 compressor/manager 向后兼容使用)
      │     ├── chat_model (ChatOpenAI, 各节点统一调用入口)
      │     ├── experts (dict[str, BaseExpertAgent])
      │     ├── responder (ResponderAgent → compressor)
      │     ├── reviewer (ReviewerAgent → memory_manager)
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
from nexus.agent.nodes.responder_node import ResponderNode
from nexus.agent.nodes.reviewer_node import ReviewerNode
from nexus.agent.nodes.supervisor_node import SupervisorNode
from nexus.agent.output_gateway import validate_output
from nexus.agent.responder import ResponderAgent
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

    本类仅保留编排入口职责（初始化 + invoke/stream），
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

        # ChatOpenAI 实例（各节点统一调用入口）
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

        作用：执行阈值压缩后用压缩历史替换原始历史，确保 SessionStore 持久化压缩后数据；
        场景：非流式调用场景，等待全部节点完成后返回完整状态。

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

        # 阈值压缩后用压缩历史（含新轮次）替换原始历史，供 SessionStore 持久化
        compressed = result.pop("_compressed_history", None)
        if compressed is not None:
            result["history"] = compressed

        return result

    async def stream(self, state: SupervisorState) -> AsyncGenerator[str, None]:
        """流式执行工作流，逐块输出响应文本。

        全链路强制闭环:
            1. Supervisor 节点（记忆+路由+分派，不输出）
            2. 专家并行执行（不输出）
            3. Responder 生成回复
            4. Reflection 反思校验（所有分支，含车控/澄清）
            5. Reviewer 终审校验（同步阻塞，全局唯一出口关卡）
            6. Output Gateway 全局输出网关校验
            7. 输出最终验证后的文本

        Args:
            state: SupervisorState 字典

        Yields:
            响应文本块（经过全链路校验后的安全文本）
        """
        # Phase 1: Supervisor
        supervisor_update = await self.supervisor_node.run(state)
        state.update(supervisor_update)

        # Phase 2: 429 错误短路消除 — LLM 不可用时仍走 Output Gateway
        llm_error = state.get("intent", {}).get("LLM_Error", "")
        if llm_error:
            fallback_msg = "抱歉，AI 服务暂时繁忙，请稍后再试。"
            state["final_response"] = fallback_msg
            # 即使是错误兜底，也要走 Reviewer + Output Gateway
            reviewer_update = await self.reviewer_node.run(state)
            state.update(reviewer_update)
            validated, gw_meta = validate_output(fallback_msg, state, reflection_passed=False)
            state["final_response"] = validated
            state.setdefault("metadata", {}).update(gw_meta)
            yield validated
            logger.warning(f"LLM unavailable, fallback through full chain: {llm_error}")
            return

        # Phase3：澄清分支——走完整Reflection + Reviewer + Gateway
        if state.get("need_clarification") and state.get("clarification_prompt"):
            full_response = state["clarification_prompt"]
            state["final_response"] = full_response
            # Reflection校验（澄清类也校验）
            reflection_update = await self.reflection_node.run(state)
            if reflection_update.get("final_response"):
                full_response = reflection_update["final_response"]
                state["final_response"] = full_response
            if reflection_update.get("metadata"):
                state.setdefault("metadata", {}).update(reflection_update["metadata"])
            # Reviewer 同步终审
            reviewer_update = await self.reviewer_node.run(state)
            state.update(reviewer_update)
            # Output Gateway 全局校验
            validated, gw_meta = validate_output(full_response, state, reflection_passed=True)
            state["final_response"] = validated
            state.setdefault("metadata", {}).update(gw_meta)
            yield validated
            return

        # Phase4：专家并行执行
        if state.get("active_experts"):
            dispatch_update = await self.dispatch_node.run(state)
            state.update(dispatch_update)

        # Phase 5: Responder 生成回复 + Reflection 校验（所有分支）
        full_response = ""

        if state.get("skill_handled"):
            # B1: 搜索类技能 → LLM 生成
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                full_response = await self.responder_node.generate_llm_response(state)

            # B2: 工具返回结构化数据 → Tool→LLM 合成
            elif state.get("tool_result") and state.get("tool_result", {}).get("data"):
                full_response = await self.responder_node.synthesize_tool_response(state)

            # B3: 简单车控指令 — 聚合所有专家回复，避免多动作场景下只输出首条回复
            else:
                expert_results = state.get("expert_results", [])
                expert_replies: dict[str, list[str]] = {}
                for er in expert_results:
                    if er.get("handled") and er.get("reply"):
                        expert_name = er.get("expert", "unknown")
                        expert_replies.setdefault(expert_name, []).append(er["reply"])
                replies = []
                for expert_name, parts in expert_replies.items():
                    if len(parts) == 1:
                        replies.append(parts[0])
                    else:
                        replies.append("；".join(parts))
                full_response = "\n".join(replies) if replies else ""

        # 分支 B4：作用：车控任务执行后调用LLM生成对话查询内容，合并两份应答数据；场景：用户同时提交车控操作、历史对话查询的复合请求
        if (
            full_response
            and state.get("intent", {}).get("History_Query_Action")
            and "chat" in state.get("active_experts", [])
        ):
            try:
                llm_response = await self.responder_node.generate_llm_response(state)
                if llm_response and llm_response.strip():
                    full_response = f"{full_response}\n{llm_response}"
                    logger.info(
                        f"Mixed-response aggregated: vehicle_reply_len={len(full_response.splitlines()[0])}, "
                        f"llm_response_len={len(llm_response)}, total_len={len(full_response)}"
                    )
            except Exception as e:
                logger.error(f"Mixed-response LLM generation failed: {e}, using vehicle reply only")

        # 分支 B5：作用：车控任务执行后调用LLM合成搜索结果，合并车控与搜索两份应答数据；场景：用户同时提交车控操作、生活搜索查询的复合请求
        if (
            full_response
            and state.get("search_context")
            and "lifestyle" in state.get("active_experts", [])
            and state.get("skill_action") != "web_search"  # 避免与 B1 重复
        ):
            try:
                original_action = state.get("skill_action", "")
                state["skill_action"] = "web_search"
                search_response = await self.responder_node.generate_llm_response(state)
                state["skill_action"] = original_action
                if search_response and search_response.strip():
                    full_response = f"{full_response}\n{search_response}"
                    logger.info(
                        f"Compound search synthesis (stream): search_len={len(search_response)}, "
                        f"total_len={len(full_response)}"
                    )
            except Exception as e:
                logger.error(f"Compound search synthesis failed (stream): {e}")

        # 分支 C: LLM 闲聊
        if not full_response:
            full_response = await self.responder_node.generate_llm_response(state)

        state["final_response"] = full_response

        # Phase6：Reflection反思校验（所有分支，含B3车控）
        reflection_update = await self.reflection_node.run(state)
        if reflection_update.get("final_response"):
            full_response = reflection_update["final_response"]
            state["final_response"] = full_response
        if reflection_update.get("metadata"):
            state.setdefault("metadata", {}).update(reflection_update["metadata"])

        # Phase 7: Reviewer 终审强校验（同步阻塞）
        # 设置五层链路完成标记，供 Reviewer 内部 validate_output 校验
        state["_chain_completed"] = True
        reviewer_update = await self.reviewer_node.run(state)
        state.update(reviewer_update)

        # Phase 8: Output Gateway 全局输出网关校验
        reflection_result = state.get("metadata", {}).get("reflection_result", "")
        reflection_passed = "passed" in reflection_result or reflection_result in ("", "chat_fast_skipped", "chat_timeout", "search_timeout", "tool_fast_skipped", "tool_timeout")
        validated, gw_meta = validate_output(full_response, state, reflection_passed=reflection_passed)
        state["final_response"] = validated
        state.setdefault("metadata", {}).update(gw_meta)

        # 更新历史
        new_turn = [
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": validated},
        ]
        if "_compressed_history" in state:
            state["history"] = state["_compressed_history"] + new_turn
        else:
            state.setdefault("history", []).extend(new_turn)

        yield validated

    @observe(name="supervisor-stream-with-events")
    async def stream_with_events(self, state: SupervisorState) -> AsyncGenerator[dict, None]:
        """流式执行工作流，输出结构化事件。

        全链路强制闭环（不可绕过）:
            1. Supervisor（记忆+路由+分派决策）
            2. Dispatch（专家并行执行）
            3. Responder（回复生成）
            4. Reflection（反思校验 — 所有分支，含车控/澄清/错误兜底）
            5. Reviewer（终审强校验 — 同步阻塞，不再后台异步）
            6. Output Gateway（全局输出网关 — 最终安全校验）
            7. 输出 chunk + done 事件（仅校验通过后）

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

        # Phase 2: 429 错误处理 — 不再短路，走完整 Reviewer + Output Gateway
        llm_error = state.get("intent", {}).get("LLM_Error", "")
        if llm_error:
            fallback_msg = "抱歉，AI 服务暂时繁忙，请稍后再试。"
            state["final_response"] = fallback_msg
            # Reviewer 同步终审（记录指标 + 记忆存储）
            reviewer_update = await self.reviewer_node.run(state)
            state.update(reviewer_update)
            # Output Gateway 全局校验
            validated, gw_meta = validate_output(fallback_msg, state, reflection_passed=False)
            state["final_response"] = validated
            state.setdefault("metadata", {}).update(gw_meta)
            yield {"type": "chunk", "data": {"chunk": validated}}
            yield {
                "type": "done",
                "data": {
                    "response": validated,
                    "latency_ms": state.get("latency_ms", 0),
                    "intent": "error",
                    "action": "",
                },
            }
            logger.warning(f"LLM unavailable, fallback through full chain: {llm_error}")
            return

        # Phase3：澄清分支——走完整Reflection + Reviewer + Gateway
        if state.get("need_clarification") and state.get("clarification_prompt"):
            full_response = state["clarification_prompt"]
            state["final_response"] = full_response
            # Reflection校验（澄清类也校验）
            reflection_update = await self.reflection_node.run(state)
            if reflection_update.get("final_response"):
                full_response = reflection_update["final_response"]
                state["final_response"] = full_response
            if reflection_update.get("metadata"):
                state.setdefault("metadata", {}).update(reflection_update["metadata"])
            # Reviewer 同步终审
            reviewer_update = await self.reviewer_node.run(state)
            state.update(reviewer_update)
            # Output Gateway 全局校验
            validated, gw_meta = validate_output(full_response, state, reflection_passed=True)
            state["final_response"] = validated
            state.setdefault("metadata", {}).update(gw_meta)
            yield {"type": "chunk", "data": {"chunk": validated}}
            yield {
                "type": "done",
                "data": {
                    "response": validated,
                    "latency_ms": state.get("latency_ms", 0),
                },
            }
            return

        # Phase4：专家并行执行
        if state.get("active_experts"):
            yield {"type": "experts", "data": {"experts": state["active_experts"]}}
            dispatch_update = await self.dispatch_node.run(state)
            state.update(dispatch_update)
            if state.get("skill_action"):
                yield {"type": "action", "data": {"action": state["skill_action"]}}

        # Phase 5: Responder 生成回复（所有分支统一处理）
        full_response = ""

        if state.get("skill_handled"):
            # B1: 搜索类技能 → LLM 生成
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                yield {"type": "thinking", "data": {"message": "正在分析搜索结果..."}}
                full_response = await self.responder_node.generate_llm_response(state)

            # B2: 工具返回结构化数据 → Tool→LLM 合成
            elif state.get("tool_result") and state.get("tool_result", {}).get("data"):
                yield {"type": "thinking", "data": {"message": "正在分析工具结果..."}}
                full_response = await self.responder_node.synthesize_tool_response(state)

            # B3: 简单车控指令 — 聚合所有专家回复，避免多动作场景下只输出首条回复
            else:
                expert_results = state.get("expert_results", [])
                expert_replies: dict[str, list[str]] = {}
                for er in expert_results:
                    if er.get("handled") and er.get("reply"):
                        expert_name = er.get("expert", "unknown")
                        expert_replies.setdefault(expert_name, []).append(er["reply"])
                replies = []
                for expert_name, parts in expert_replies.items():
                    if len(parts) == 1:
                        replies.append(parts[0])
                    else:
                        replies.append("；".join(parts))
                full_response = "\n".join(replies) if replies else ""

        # 分支 B4：作用：车控任务执行后调用LLM生成对话查询内容，合并两份应答数据；场景：用户同时提交车控操作、历史对话查询的复合请求
        if (
            full_response
            and state.get("intent", {}).get("History_Query_Action")
            and "chat" in state.get("active_experts", [])
        ):
            try:
                yield {"type": "thinking", "data": {"message": "正在回顾对话历史..."}}
                llm_response = await self.responder_node.generate_llm_response(state)
                if llm_response and llm_response.strip():
                    full_response = f"{full_response}\n{llm_response}"
                    logger.info(
                        f"Mixed-response aggregated (events): "
                        f"llm_response_len={len(llm_response)}, total_len={len(full_response)}"
                    )
            except Exception as e:
                logger.error(f"Mixed-response LLM generation failed (events): {e}")

        # 分支 B5：作用：车控任务执行后调用LLM合成搜索结果，合并车控与搜索两份应答数据；场景：用户同时提交车控操作、生活搜索查询的复合请求
        if (
            full_response
            and state.get("search_context")
            and "lifestyle" in state.get("active_experts", [])
            and state.get("skill_action") != "web_search"  # 避免与 B1 重复
        ):
            try:
                yield {"type": "thinking", "data": {"message": "正在分析搜索结果..."}}
                original_action = state.get("skill_action", "")
                state["skill_action"] = "web_search"
                search_response = await self.responder_node.generate_llm_response(state)
                state["skill_action"] = original_action
                if search_response and search_response.strip():
                    full_response = f"{full_response}\n{search_response}"
                    logger.info(
                        f"Compound search synthesis (events): search_len={len(search_response)}, "
                        f"total_len={len(full_response)}"
                    )
            except Exception as e:
                logger.error(f"Compound search synthesis failed (events): {e}")

        # 分支 C: LLM 闲聊
        if not full_response:
            yield {"type": "thinking", "data": {"message": "正在生成回复..."}}
            full_response = await self.responder_node.generate_llm_response(state)

        state["final_response"] = full_response

        # Phase6：Reflection反思校验（所有分支，含B3车控）
        yield {"type": "thinking", "data": {"message": "正在校验回复质量..."}}
        reflection_update = await self.reflection_node.run(state)
        if reflection_update.get("final_response"):
            full_response = reflection_update["final_response"]
            state["final_response"] = full_response
        if reflection_update.get("metadata"):
            state.setdefault("metadata", {}).update(reflection_update["metadata"])

        # Phase 7: Reviewer 终审强校验（同步阻塞）
        # 设置五层链路完成标记，供 Reviewer 内部 validate_output 校验
        state["_chain_completed"] = True
        reviewer_update = await self.reviewer_node.run(state)
        state.update(reviewer_update)

        # Phase 8: Output Gateway 全局输出网关校验：未通过校验内容不输出前端
        reflection_result = state.get("metadata", {}).get("reflection_result", "")
        reflection_passed = "passed" in reflection_result or reflection_result in ("", "chat_fast_skipped", "chat_timeout", "search_timeout", "tool_fast_skipped", "tool_timeout")
        validated, gw_meta = validate_output(full_response, state, reflection_passed=reflection_passed)
        state["final_response"] = validated
        state.setdefault("metadata", {}).update(gw_meta)

        # 更新历史 — 如果执行了阈值压缩，使用压缩后的历史作为基础
        new_turn = [
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": validated},
        ]
        if "_compressed_history" in state:
            state["history"] = state["_compressed_history"] + new_turn
        else:
            state.setdefault("history", []).extend(new_turn)

        # Phase 9: 发送 chunk + done 事件（仅校验通过后）
        metadata = state.get("metadata", {})
        total_latency = sum(
            metadata.get(k, 0)
            for k in metadata
            if k.endswith("_latency_ms")
        )
        state["latency_ms"] = round(total_latency, 2)

        yield {"type": "chunk", "data": {"chunk": validated}}

        yield {
            "type": "done",
            "data": {
                "response": validated,
                "latency_ms": state.get("latency_ms", 0),
                "intent": intent_name,
                "action": state.get("skill_action", ""),
            },
        }

        # Reviewer 记忆存储已在 Phase 7 同步完成
