"""
Supervisor Graph — v2.0 Multi-Agent 工作流编排核心

替代 v1.0 的 AgentGraph（线性 Planner→Executor→Responder→Reviewer），
升级为 Supervisor 调度 + 5 专家并行 + Responder 汇总 + Reviewer 审查。

图结构:
    supervisor → [条件分派] → vehicle_expert  ↘
                          → nav_expert         → responder → reviewer → END
                          → lifestyle_expert  ↗
                          → health_expert     ↗
                          → chat_expert       ↗
                          → responder (澄清/无专家时直连)

Supervisor 职责:
    1. 记忆召回
    2. 意图路由（复用 IntentRouterService）
    3. 判断需要哪些专家 → 设置 active_experts
    4. 澄清判断

专家并行:
    所有活跃专家通过 LangGraph 并行节点同时执行，
    expert_results 通过 Annotated[list, add] reducer 自动累加。
"""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any, AsyncGenerator, Dict, List, Optional

from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI

from nexus.agent.experts import (
    ChatExpert,
    HealthExpert,
    LifestyleExpert,
    NavExpert,
    VehicleExpert,
)
from nexus.agent.experts.base import BaseExpertAgent
from nexus.agent.responder import ResponderAgent
from nexus.agent.reviewer import ReviewerAgent
from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.intent.router import IntentRouterService
from nexus.memory.compressor import ContextCompressor
from nexus.memory.manager import MemoryManager
from nexus.models.state import SupervisorState, create_initial_state
from nexus.prompts import PromptManager
from nexus.skills.registry import SkillRegistry

logger = get_logger(__name__)


class SupervisorGraph:
    """v2.0 Supervisor 多智能体工作流编排器。

    使用 LangGraph StateGraph 构建 Supervisor → Experts → Responder → Reviewer 工作流。
    支持 invoke()（同步）和 stream()（流式）两种调用模式。

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
        llm_client: Optional[AsyncOpenAI] = None,
        checkpoint_saver=None,
    ):
        self.intent_router = intent_router
        self.memory_manager = memory_manager
        self.skill_registry = skill_registry

        # LLM 客户端
        config = get_config().llm
        self.llm_client = llm_client or AsyncOpenAI(
            api_key=config.ark_api_key,
            base_url=config.ark_base_url,
        )

        # 初始化 5 个专家
        self.experts: Dict[str, BaseExpertAgent] = {
            "vehicle": VehicleExpert(skill_registry),
            "navigation": NavExpert(skill_registry),
            "lifestyle": LifestyleExpert(skill_registry),
            "health": HealthExpert(skill_registry),
            "chat": ChatExpert(skill_registry),
        }

        # Responder 和 Reviewer 复用 v1.0 实现
        self.responder = ResponderAgent(self.llm_client)
        self.reviewer = ReviewerAgent(memory_manager)

        # v2.0 Prompt 模板管理器
        self.prompt_manager = PromptManager()

        # Checkpoint 持久化
        self.checkpoint_saver = checkpoint_saver

        # 构建 LangGraph 图
        self._graph = self._build_graph()

    def _build_graph(self):
        """构建 LangGraph 有向图工作流。"""
        workflow = StateGraph(SupervisorState)

        # ---- 注册节点 ----
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("vehicle_expert", self.experts["vehicle"].run)
        workflow.add_node("nav_expert", self.experts["navigation"].run)
        workflow.add_node("lifestyle_expert", self.experts["lifestyle"].run)
        workflow.add_node("health_expert", self.experts["health"].run)
        workflow.add_node("chat_expert", self.experts["chat"].run)
        workflow.add_node("responder", self._responder_node)
        workflow.add_node("reviewer", self._reviewer_node)

        # ---- 入口 ----
        workflow.set_entry_point("supervisor")

        # ---- 条件边: Supervisor → 专家群 or 直连 Responder ----
        workflow.add_conditional_edges(
            "supervisor",
            self._route_from_supervisor,
            {
                "dispatch": "dispatch",
                "responder": "responder",
            },
        )

        # ---- 专家群 → Responder（全部汇聚）----
        # 使用条件边返回的 "dispatch" 标记触发所有专家
        # 由于 LangGraph 条件边只能返回单个目标，
        # 我们用 "dispatch" 路由到第一个专家，然后链式连接
        # 实际并行通过 _dispatch_node 实现
        workflow.add_node("dispatch", self._dispatch_node)
        workflow.add_edge("dispatch", "responder")

        # ---- Responder → Reviewer → END ----
        workflow.add_edge("responder", "reviewer")
        workflow.add_edge("reviewer", END)

        # 编译图（可选 checkpoint）
        compile_kwargs = {}
        if self.checkpoint_saver:
            compile_kwargs["checkpointer"] = self.checkpoint_saver
        return workflow.compile(**compile_kwargs)

    def _route_from_supervisor(self, state: SupervisorState) -> str:
        """Supervisor 条件路由：需要分派专家时走 dispatch，否则直连 responder。"""
        if state.get("need_clarification"):
            return "responder"
        if not state.get("active_experts"):
            return "responder"
        return "dispatch"

    async def _supervisor_node(self, state: SupervisorState) -> Dict[str, Any]:
        """Supervisor 节点：记忆召回 + 意图路由 + 专家分派决策。

        Returns:
            Partial state update
        """
        t0 = perf_counter()
        update: Dict[str, Any] = {
            "recalled_memories": [],
            "memory_str": "",
            "intent": {},
            "intent_source": "default",
            "need_clarification": False,
            "clarification_prompt": "",
            "active_experts": [],
            "expert_results": [],
        }

        # 1. 记忆召回
        try:
            memories = await self.memory_manager.recall(
                state.get("user_input", ""), state.get("user_id", "default"), top_k=5
            )
            update["recalled_memories"] = memories
            user_id = state.get("user_id", "default")
            update["memory_str"] = (
                f"【关于 {user_id} 的记忆】: {';'.join(memories)}"
                if memories
                else ""
            )
        except Exception as e:
            logger.error(f"Memory recall failed: {e}")

        # 2. 意图路由
        try:
            intent = await self.intent_router.route(state.get("user_input", ""))
            update["intent"] = intent
            update["intent_source"] = intent.get("Route_Source", "default")
            update["need_clarification"] = intent.get("Need_Clarification", False)
            update["clarification_prompt"] = intent.get("Clarification_Prompt", "")
        except Exception as e:
            logger.error(f"Intent routing failed: {e}")
            update["intent_source"] = "error"

        # 3. 决策分派给哪些专家
        if not update["need_clarification"]:
            update["active_experts"] = self._determine_experts(update["intent"])

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        update["metadata"] = {"supervisor_latency_ms": latency_ms}

        logger.info(
            f"Supervisor done: source={update['intent_source']}, "
            f"experts={update['active_experts']}, "
            f"clarify={update['need_clarification']}, "
            f"latency={latency_ms}ms"
        )
        return update

    def _determine_experts(self, intent: Dict[str, Any]) -> List[str]:
        """根据意图路由结果决定分派给哪些专家。

        策略:
          - 车控动作 → vehicle
          - 导航动作 → navigation
          - 搜索/点餐 → lifestyle
          - 声纹注册 → chat
          - 无匹配 → chat（闲聊兜底）

        Returns:
            专家名称列表
        """
        experts: List[str] = []

        # 车控
        vehicle_keys = (
            "Climate_Action", "Window_Action", "Seat_Action",
            "Media_Action", "Vehicle_Status_Action",
        )
        if any(intent.get(k) for k in vehicle_keys):
            experts.append("vehicle")

        # 导航
        if intent.get("Navigation_Action"):
            experts.append("navigation")

        # 生活推荐（搜索/点餐）
        if intent.get("Need_Search") or intent.get("Call_elm"):
            experts.append("lifestyle")

        # 声纹注册
        if intent.get("Register_Action"):
            experts.append("chat")

        # 无匹配 → 闲聊兜底
        if not experts:
            experts.append("chat")

        return experts

    async def _dispatch_node(self, state: SupervisorState) -> Dict[str, Any]:
        """专家并行分派节点：同时执行所有活跃专家。

        使用 asyncio.gather 并行调用所有活跃专家的 run() 方法，
        合并所有 partial updates 为一个最终 update。
        expert_results 通过 reducer 自动累加。
        """
        active_experts = state.get("active_experts", [])
        if not active_experts:
            return {}

        # 并行执行所有活跃专家
        tasks = []
        expert_names = []
        for name in active_experts:
            expert = self.experts.get(name)
            if expert:
                tasks.append(expert.run(state))
                expert_names.append(name)

        if not tasks:
            return {}

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并所有专家的 partial updates
        merged: Dict[str, Any] = {"expert_results": []}
        merged_metadata: Dict[str, Any] = {}

        for name, result in zip(expert_names, results):
            if isinstance(result, Exception):
                logger.error(f"Expert '{name}' raised: {result}")
                merged["expert_results"].append({
                    "expert": name,
                    "action": "",
                    "reply": "",
                    "handled": False,
                    "error": str(result),
                })
                merged_metadata[f"{name}_error"] = str(result)
            elif isinstance(result, dict):
                # 累加 expert_results
                if "expert_results" in result:
                    merged["expert_results"].extend(result["expert_results"])
                # 取最后一个非空 skill_action / skill_handled / search_context
                for key in ("skill_action", "skill_handled", "search_context"):
                    if result.get(key) is not None:
                        if key == "skill_handled" and result[key]:
                            merged[key] = True
                        elif key == "search_context" and result[key]:
                            merged[key] = result[key]
                        elif key == "skill_action" and result[key]:
                            merged[key] = result[key]
                # 合并 metadata
                if "metadata" in result:
                    merged_metadata.update(result["metadata"])

        if merged_metadata:
            merged["metadata"] = merged_metadata

        # 确保 skill_handled 有默认值
        merged.setdefault("skill_handled", False)
        merged.setdefault("skill_action", "")
        merged.setdefault("search_context", "")

        logger.info(
            f"Dispatch done: {len(active_experts)} experts, "
            f"{len(merged['expert_results'])} results, "
            f"handled={merged.get('skill_handled', False)}"
        )
        return merged

    async def _responder_node(self, state: SupervisorState) -> Dict[str, Any]:
        """Responder 节点：汇总专家输出，生成最终回复。

        适配 v1.0 ResponderAgent，从 expert_results 中提取回复内容。
        """
        t0 = perf_counter()
        full_response = ""

        # 分支 A: 需要澄清
        if state.get("need_clarification") and state.get("clarification_prompt"):
            full_response = state["clarification_prompt"]

        # 分支 B: 专家已处理
        elif state.get("skill_handled"):
            expert_results = state.get("expert_results", [])
            # 找到第一个 handled=True 的专家结果
            for er in expert_results:
                if er.get("handled") and er.get("reply"):
                    full_response = er["reply"]
                    break

            # 搜索类技能需要 LLM 组织回答
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                full_response = await self._generate_llm_response(state)

        # 分支 C: LLM 闲聊兜底
        else:
            full_response = await self._generate_llm_response(state)

        # 更新历史
        history_update = [
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": full_response},
        ]

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        logger.info(f"Responder done: response_len={len(full_response)}, latency={latency_ms}ms")

        return {
            "final_response": full_response,
            "history": history_update,
            "metadata": {"responder_latency_ms": latency_ms},
        }

    async def _generate_llm_response(self, state: SupervisorState) -> str:
        """调用 LLM 生成回复（非流式）。"""
        system_msg = self.prompt_manager.render(
            "chat",
            user_profile=state.get("user_profile", {}),
            memory=state.get("memory_str", ""),
        ) or "你叫小千，是一个活泼可爱的车载语音助手。请结合上下文极简回答用户，不超过30字。"

        msgs, new_summary = await self.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=state.get("history", []),
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=state.get("search_context", ""),
        )

        try:
            response = await self.llm_client.chat.completions.create(
                model=get_config().llm.llm_model,
                messages=msgs,
                temperature=0.7,
                max_tokens=get_config().llm.max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM response failed: {e}")
            return f"抱歉，我遇到了一些问题: {e}"

    async def _stream_llm_response(self, state: SupervisorState) -> AsyncGenerator[str, None]:
        """流式调用 LLM 生成回复。"""
        system_msg = self.prompt_manager.render(
            "chat",
            user_profile=state.get("user_profile", {}),
            memory=state.get("memory_str", ""),
        ) or "你叫小千，是一个活泼可爱的车载语音助手。请结合上下文极简回答用户，不超过30字。"

        msgs, new_summary = await self.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=state.get("history", []),
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=state.get("search_context", ""),
        )

        try:
            response = await self.llm_client.chat.completions.create(
                model=get_config().llm.llm_model,
                messages=msgs,
                stream=True,
                temperature=0.7,
                max_tokens=get_config().llm.max_tokens,
            )
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            yield f"抱歉，连接模型出错: {e}"

    async def _reviewer_node(self, state: SupervisorState) -> Dict[str, Any]:
        """Reviewer 节点：质量检查 + 记忆存储 + 延迟统计。"""
        t0 = perf_counter()
        update: Dict[str, Any] = {}

        # 1. 响应质量检查
        final_response = state.get("final_response", "")
        if not final_response or len(final_response.strip()) < 2:
            update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
            update["metadata"] = {"reviewer_fallback": True}

        # 2. 触发后台记忆存储
        if self.memory_manager and final_response:
            try:
                self.memory_manager.store_from_text_async(
                    state.get("user_input", ""), state.get("user_id", "default")
                )
                update.setdefault("metadata", {})["memory_storage_triggered"] = True
            except Exception as e:
                logger.error(f"Memory storage trigger failed: {e}")

        # 3. 计算总延迟
        metadata = state.get("metadata", {})
        reviewer_latency = round((perf_counter() - t0) * 1000, 2)
        total_latency = sum(
            metadata.get(k, 0)
            for k in (
                "supervisor_latency_ms",
                "responder_latency_ms",
                "reviewer_latency_ms",
            )
        )
        # 也检查专家的延迟
        for key in metadata:
            if key.endswith("_latency_ms") and key not in (
                "supervisor_latency_ms", "responder_latency_ms", "reviewer_latency_ms"
            ):
                total_latency += metadata[key]

        update["latency_ms"] = round(total_latency, 2)
        update.setdefault("metadata", {})["reviewer_latency_ms"] = reviewer_latency
        update["metadata"]["total_latency_ms"] = update["latency_ms"]

        logger.info(
            f"Reviewer done: total_latency={update['latency_ms']}ms, "
            f"response='{final_response[:50]}...'"
        )
        return update

    # ---- 公共接口 ----

    async def invoke(self, state: SupervisorState) -> SupervisorState:
        """同步执行整个工作流（等待全部完成）。

        Args:
            state: SupervisorState 字典（用 create_initial_state 创建）

        Returns:
            完成后的完整 SupervisorState
        """
        result = await self._graph.ainvoke(state)
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
        supervisor_update = await self._supervisor_node(state)
        state.update(supervisor_update)

        # Phase 2: 澄清分支
        if state.get("need_clarification") and state.get("clarification_prompt"):
            yield state["clarification_prompt"]
            state["final_response"] = state["clarification_prompt"]
            reviewer_update = await self._reviewer_node(state)
            state.update(reviewer_update)
            return

        # Phase 3: 专家并行执行
        if state.get("active_experts"):
            dispatch_update = await self._dispatch_node(state)
            state.update(dispatch_update)

        # Phase 4: 流式响应
        full_response = ""

        # 分支 B: 技能已处理（非搜索类）
        if state.get("skill_handled"):
            expert_results = state.get("expert_results", [])
            for er in expert_results:
                if er.get("handled") and er.get("reply"):
                    full_response = er["reply"]
                    yield full_response
                    break

        # 分支 C: 搜索类 / LLM 闲聊
        if not full_response:
            async for chunk in self._stream_llm_response(state):
                full_response += chunk
                yield chunk

        state["final_response"] = full_response

        # 更新历史
        state.setdefault("history", []).extend([
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": full_response},
        ])

        # Phase 5: 审查后处理
        reviewer_update = await self._reviewer_node(state)
        state.update(reviewer_update)

    async def stream_with_events(self, state: SupervisorState) -> AsyncGenerator[dict, None]:
        """流式执行工作流，输出结构化事件（v2.0 新增）。

        事件类型:
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
        import json

        # Phase 1: Supervisor
        supervisor_update = await self._supervisor_node(state)
        state.update(supervisor_update)

        # 发送意图事件
        intent_name = state.get("intent_source", "")
        yield {"type": "intent", "data": {"intent": intent_name, "source": intent_name}}

        # Phase 2: 澄清分支
        if state.get("need_clarification") and state.get("clarification_prompt"):
            yield {"type": "chunk", "data": {"chunk": state["clarification_prompt"]}}
            state["final_response"] = state["clarification_prompt"]
            reviewer_update = await self._reviewer_node(state)
            state.update(reviewer_update)
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
            dispatch_update = await self._dispatch_node(state)
            state.update(dispatch_update)
            if state.get("skill_action"):
                yield {"type": "action", "data": {"action": state["skill_action"]}}

        # Phase 4: 流式响应
        full_response = ""

        if state.get("skill_handled"):
            expert_results = state.get("expert_results", [])
            for er in expert_results:
                if er.get("handled") and er.get("reply"):
                    full_response = er["reply"]
                    yield {"type": "chunk", "data": {"chunk": full_response}}
                    break

        if not full_response:
            async for chunk in self._stream_llm_response(state):
                full_response += chunk
                yield {"type": "chunk", "data": {"chunk": chunk}}

        state["final_response"] = full_response
        state.setdefault("history", []).extend([
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": full_response},
        ])

        # Phase 5: 审查后处理
        reviewer_update = await self._reviewer_node(state)
        state.update(reviewer_update)

        yield {
            "type": "done",
            "data": {
                "response": state["final_response"],
                "latency_ms": state.get("latency_ms", 0),
                "intent": intent_name,
                "action": state.get("skill_action", ""),
            },
        }
