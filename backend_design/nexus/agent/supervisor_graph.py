# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Supervisor Graph — v2.0 Multi-Agent 工作流编排核心

替代 v1.0 的 AgentGraph（线性 Planner→Executor→Responder→Reviewer），
升级为 Supervisor 调度 + 5 专家并行 + Responder 汇总 + Reviewer 审查。

图结构:
    supervisor → [条件分派] → vehicle_expert  ↘
                          → nav_expert         → responder → reflection → reviewer → END
                          → lifestyle_expert  ↗
                          → health_expert     ↗
                          → chat_expert       ↗
                          → responder (澄清/无专家时直连)

v2.2 增强:
    - Tool→LLM 合成: 工具调用结果回传 LLM 生成自然语言回复
    - 反思校验: 对 LLM 输出做事实性/一致性/无幻觉检查
    - 自我批评: 反思不通过时自动修正回复

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
import json
import re
from time import perf_counter
from typing import Any, AsyncGenerator, Dict, List, Optional

import redis.asyncio as aioredis
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
from nexus.agent.mainagent_confirm import MainAgentConfirmLayer
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
        redis_client: Redis 客户端（v2.1 MainAgent 确认层需要，可选）
    """

    def __init__(
        self,
        intent_router: IntentRouterService,
        memory_manager: MemoryManager,
        skill_registry: SkillRegistry,
        llm_client: Optional[AsyncOpenAI] = None,
        checkpoint_saver=None,
        redis_client: Optional[aioredis.Redis] = None,
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

        # 【v2.1 新增】MainAgent 确认层（需要 redis_client 用于快通道查询和 Pub/Sub）
        self.mainagent_confirm = MainAgentConfirmLayer(
            llm_client=self.llm_client,
            redis_client=redis_client,
        )
        if redis_client is None:
            logger.warning(
                "MainAgentConfirmLayer initialized without redis_client — "
                "fast-path checks and Pub/Sub will be disabled until redis is set"
            )

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
        workflow.add_node("reflection", self._reflection_node)  # v2.2
        workflow.add_node("mainagent_confirm", self._mainagent_confirm_node)  # v2.1
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

        # ---- v2.2: Responder → Reflection → MainAgent Confirm → Reviewer → END ----
        workflow.add_edge("responder", "reflection")       # responder → reflection
        workflow.add_edge("reflection", "mainagent_confirm") # reflection → confirm
        workflow.add_edge("mainagent_confirm", "reviewer")   # confirm → reviewer
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
        """Supervisor 节点：记忆召回 + 用户画像加载 + 意图路由 + 专家分派决策。

        v2.1 增强:
            - 记忆召回改用 GraphRAG 三路融合 + Rerank
            - 加载用户画像（Neo4j）和习惯（MySQL）
            - 习惯记忆注入到 state，供 prompt 使用

        Returns:
            Partial state update
        """
        t0 = perf_counter()
        update: Dict[str, Any] = {
            "recalled_memories": [],
            "memory_str": "",
            "habits_str": "",
            "user_profile": {},
            "intent": {},
            "intent_source": "default",
            "need_clarification": False,
            "clarification_prompt": "",
            "active_experts": [],
            "expert_results": [],
        }

        user_id = state.get("user_id", "default")
        user_input = state.get("user_input", "")

        # v2.1 优化: 记忆召回 + 用户画像 + 意图路由 并行执行
        # 原来串行需要 3 倍时间，并行后只取最慢的一个

        async def _recall_memory():
            """记忆召回"""
            try:
                memories = await self.memory_manager.recall(user_input, user_id, top_k=3)
                return memories
            except Exception as e:
                logger.error(f"Memory recall failed: {e}")
                return []

        def _load_profile():
            """加载用户画像"""
            try:
                return self.memory_manager.get_user_profile(user_id) or {}
            except Exception as e:
                logger.error(f"User profile loading failed: {e}")
                return {}

        async def _route_intent():
            """意图路由"""
            try:
                return await self.intent_router.route(user_input)
            except Exception as e:
                logger.error(f"Intent routing failed: {e}")
                return {"Route_Source": "error"}

        # 三个任务并行执行
        memories, profile, intent = await asyncio.gather(
            _recall_memory(),
            asyncio.to_thread(_load_profile),
            _route_intent(),
        )

        # 处理记忆结果
        update["recalled_memories"] = memories
        memory_items = []
        habit_items = []
        for m in memories:
            if m.startswith("[习惯]"):
                habit_items.append(m)
            else:
                memory_items.append(m)
        update["memory_str"] = ";".join(memory_items) if memory_items else ""
        update["habits_str"] = "\n".join(habit_items) if habit_items else ""

        # 处理用户画像
        if profile:
            update["user_profile"] = profile

        # 处理意图路由结果
        update["intent"] = intent
        update["intent_source"] = intent.get("Route_Source", "default")
        update["need_clarification"] = intent.get("Need_Clarification", False)
        update["clarification_prompt"] = intent.get("Clarification_Prompt", "")

        # 4. 决策分派给哪些专家
        if not update["need_clarification"]:
            update["active_experts"] = self._determine_experts(update["intent"])

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        update["metadata"] = {"supervisor_latency_ms": latency_ms}

        logger.info(
            f"Supervisor done: source={update['intent_source']}, "
            f"experts={update['active_experts']}, "
            f"memories={len(update['recalled_memories'])}, "
            f"profile={'yes' if update['user_profile'] else 'no'}, "
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
                # v2.2: 传递 tool_result 到顶层 state
                if result.get("tool_result"):
                    merged["tool_result"] = result["tool_result"]
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

        v2.2 增强:
            - 分支 B 优化: 当工具返回结构化数据时，将结果回传 LLM 做自然语言合成
            - 不再直接返回原始工具消息，而是经过 LLM 解读后输出
        """
        t0 = perf_counter()
        full_response = ""

        # 分支 A: 需要澄清
        if state.get("need_clarification") and state.get("clarification_prompt"):
            full_response = state["clarification_prompt"]

        # 分支 B: 专家已处理
        elif state.get("skill_handled"):
            # B1: 搜索类技能用专用 search 提示词
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                full_response = await self._generate_llm_response(state)

            # B2: v2.2 工具返回了结构化数据 → Tool→LLM 合成
            elif state.get("tool_result") and state.get("tool_result", {}).get("data"):
                full_response = await self._synthesize_tool_response(state)

            # B3: 简单车控指令，直接使用工具返回的自然语言消息
            else:
                expert_results = state.get("expert_results", [])
                for er in expert_results:
                    if er.get("handled") and er.get("reply"):
                        full_response = er["reply"]
                        break

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

    async def _synthesize_tool_response(self, state: SupervisorState) -> str:
        """【v2.2】Tool→LLM 合成：将工具调用结果回传 LLM，生成自然语言回复。

        核心思路（CoT 模式）:
            1. 工具返回的结构化数据作为事实依据
            2. LLM 根据用户问题 + 工具结果，推理生成自然回复
            3. 确保回复基于工具真实数据，不编造额外信息

        v2.2.1 修复:
            - 工具返回失败/未知结果时跳过 LLM 合成，直接返回原始消息
            - 强化提示词，明确禁止添加天气/新闻等工具结果外的信息
            - 不注入记忆和习惯，避免 LLM 基于历史记忆编造信息

        Args:
            state: 包含 tool_result、user_input 等的 SupervisorState

        Returns:
            LLM 生成的自然语言回复，或工具原始消息
        """
        tool_result = state.get("tool_result", {})
        tool_message = tool_result.get("message", "")
        tool_data = tool_result.get("data", {})
        tool_name = tool_result.get("tool_name", "")

        user_input = state.get("user_input", "")

        # v2.2.1: 工具返回失败/未知结果时，跳过 LLM 合成，直接返回原始消息
        # 避免 LLM 在“未知位置”基础上编造天气、地址等虚假信息
        failure_indicators = ("未知", "不可用", "失败", "错误", "无法", "不支持")
        if any(indicator in tool_message for indicator in failure_indicators):
            logger.info(
                f"Tool synthesis SKIPPED (failure detected): tool={tool_name}, "
                f"message={tool_message[:80]}"
            )
            return tool_message

        # 构建包含工具结果的系统提示
        system_msg = (
            "你是车载语音助手小千。你刚刚通过工具获取了真实数据，"
            "请基于以下工具返回的结果回答用户问题。\n\n"
            f"## 工具调用结果\n"
            f"- 工具名称: {tool_name}\n"
            f"- 结果摘要: {tool_message}\n"
            f"- 结构化数据: {json.dumps(tool_data, ensure_ascii=False, default=str)}\n\n"
            "## 回答要求（严格遵守）\n"
            "1. **只能基于工具返回的数据回答**，绝对禁止添加任何工具结果中没有的信息\n"
            "2. **禁止添加**天气、新闻、时事、推荐、建议等工具结果外的内容\n"
            "3. **禁止使用记忆或历史对话中的信息**来补充工具结果\n"
            "4. 用自然口语化的方式转述工具结果，像在跟用户聊天一样\n"
            "5. 回答简洁明了，直接给出用户关心的核心信息\n"
            "6. 如果工具结果已经是一句完整的话，可以自然地转述即可\n"
        )

        # v2.2.1: 不注入记忆和习惯，避免 LLM 基于历史记忆编造信息

        # 构建对话上下文
        msgs, new_summary = await self.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=user_input,
            history=state.get("history", []),
            running_summary=state.get("running_summary", ""),
            memory_str="",  # v2.2.1: 不注入记忆
            search_ctx="",
        )

        try:
            response = await self.llm_client.chat.completions.create(
                model=get_config().llm.llm_model,
                messages=msgs,
                temperature=0.3,  # 低温度确保事实准确性
                max_tokens=get_config().llm.max_tokens,
            )
            synthesized = response.choices[0].message.content.strip()
            logger.info(
                f"Tool synthesis done: tool={tool_name}, "
                f"raw_len={len(tool_message)}, synth_len={len(synthesized)}"
            )
            return synthesized
        except Exception as e:
            logger.error(f"Tool response synthesis failed: {e}, falling back to raw message")
            return tool_message  # 降级：返回原始工具消息

    async def _reflection_node(self, state: SupervisorState) -> Dict[str, Any]:
        """【v2.2】反思校验节点：对 LLM 输出做事实性、一致性、无幻觉检查。

        反思策略:
            - 有工具数据时：执行 LLM 反思（CoT 自我批评）
              1. 检查回复是否与工具数据一致（事实性）
              2. 检查回复是否包含编造信息（无幻觉）
              3. 检查回复是否回答了用户问题（相关性）
              4. 不通过时自动修正
            - 有搜索结果时：执行 LLM 反思（v2.2.2 新增）
              1. 检查回复是否基于搜索结果，无编造
              2. 检查搜索结果时效性是否被正确传达
            - 无工具数据时：轻量检查（非空、长度合理）

        v2.1.2: 可通过 REFLECTION_ENABLED=false 关闭以减少 LLM 调用。

        Args:
            state: 包含 final_response 和 tool_result 的 SupervisorState

        Returns:
            Partial state update，可能修正 final_response
        """
        t0 = perf_counter()
        tool_result = state.get("tool_result", {})
        final_response = state.get("final_response", "")
        user_input = state.get("user_input", "")
        search_context = state.get("search_context", "")

        update: Dict[str, Any] = {"metadata": {}}

        # v2.1.2: 反思开关 — 关闭时跳过所有 LLM 反思，仅做轻量检查
        if not get_config().llm.reflection_enabled:
            if not final_response or len(final_response.strip()) < 2:
                update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
                update["metadata"]["reflection_result"] = "fallback_empty"
            else:
                update["metadata"]["reflection_result"] = "disabled_by_config"
            latency_ms = round((perf_counter() - t0) * 1000, 2)
            update["metadata"]["reflection_latency_ms"] = latency_ms
            logger.info(f"Reflection skipped (disabled by config): latency={latency_ms}ms")
            return update

        # v2.2.2: 搜索类回复也做反思校验
        if not tool_result or not tool_result.get("message"):
            if search_context and state.get("skill_action") == "web_search":
                # 搜索类反思：检查回复是否基于搜索结果，是否有时效性问题
                return await self._reflect_search_response(
                    state, user_input, final_response, search_context, t0
                )
            
            # 无工具数据且无搜索结果时，做轻量检查
            if not final_response or len(final_response.strip()) < 2:
                update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
                update["metadata"]["reflection_result"] = "fallback_empty"
            else:
                update["metadata"]["reflection_result"] = "skip_no_tool_data"
            
            latency_ms = round((perf_counter() - t0) * 1000, 2)
            update["metadata"]["reflection_latency_ms"] = latency_ms
            logger.info(f"Reflection done: latency={latency_ms}ms")
            return update

        # 有工具数据时，执行 LLM 反思
        tool_message = tool_result.get("message", "")
        tool_data = tool_result.get("data", {})
        tool_name = tool_result.get("tool_name", "")

        reflection_prompt = (
            "你是一个响应质量审查员。请检查助手的回复是否准确、一致、无幻觉。\n\n"
            f"## 用户问题\n{user_input}\n\n"
            f"## 工具返回的真实数据\n"
            f"- 工具名称: {tool_name}\n"
            f"- 结果摘要: {tool_message}\n"
            f"- 详细数据: {json.dumps(tool_data, ensure_ascii=False, default=str)}\n\n"
            f"## 助手回复\n{final_response}\n\n"
            "## 检查标准（逐条分析）\n"
            "1. **事实性**: 回复中的信息是否与工具返回的数据一致？有没有歪曲数据？\n"
            "2. **完整性**: 回复是否包含了用户关心的关键信息？\n"
            "3. **无幻觉**: 回复中是否有工具数据不支持的编造信息？\n"
            "4. **相关性**: 回复是否直接回答了用户的问题？\n\n"
            "请先简要分析，然后输出以下 JSON（只输出 JSON，不要其他内容）:\n"
            '{"valid": true或false, "reason": "简短原因", '
            '"suggested_response": "如果不合格，给出修正后的回复；如果合格则留空"}'
        )

        try:
            response = await self.llm_client.chat.completions.create(
                model=get_config().llm.llm_model,
                messages=[{"role": "user", "content": reflection_prompt}],
                temperature=0.0,
                max_tokens=500,
            )
            content = (response.choices[0].message.content or "").strip()

            # 解析 JSON
            cleaned = content.replace("```json", "").replace("```", "").strip()
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
            result = json.loads(cleaned)

            if result.get("valid") is True:
                logger.info(f"Reflection PASSED: {result.get('reason', '')}")
                update["metadata"]["reflection_result"] = "passed"
                update["metadata"]["reflection_reason"] = result.get("reason", "")
            else:
                # 反思不通过，使用修正后的回复
                suggested = result.get("suggested_response", "").strip()
                if suggested:
                    logger.warning(
                        f"Reflection FAILED: {result.get('reason', '')}, "
                        f"applying corrected response"
                    )
                    update["final_response"] = suggested
                    update["metadata"]["reflection_result"] = "corrected"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")
                    update["metadata"]["original_response"] = final_response[:200]
                else:
                    logger.warning(
                        f"Reflection FAILED but no suggestion: {result.get('reason', '')}"
                    )
                    update["metadata"]["reflection_result"] = "failed_no_suggestion"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")

        except Exception as e:
            logger.error(f"Reflection LLM call failed: {e}")
            update["metadata"]["reflection_result"] = "error"
            update["metadata"]["reflection_error"] = str(e)

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        update["metadata"]["reflection_latency_ms"] = latency_ms
        logger.info(f"Reflection done: latency={latency_ms}ms")

        return update

    async def _reflect_search_response(
        self, state: SupervisorState, user_input: str,
        final_response: str, search_context: str, t0: float,
    ) -> Dict[str, Any]:
        """【v2.2.2】搜索类回复反思：检查回复是否基于搜索结果，是否正确传达时效性。

        检查项:
            1. 回复中的信息是否都能在搜索结果中找到对应（无幻觉）
            2. 回复是否正确传达了搜索结果的时效性
            3. 回复是否添加了搜索结果中不存在的具体数据（如温度、时间等）
        """
        update: Dict[str, Any] = {"metadata": {}}

        reflection_prompt = (
            "你是一个响应质量审查员。请检查助手的回复是否准确基于搜索结果。\n\n"
            f"## 用户问题\n{user_input}\n\n"
            f"## 搜索结果（真实数据）\n{search_context[:2000]}\n\n"
            f"## 助手回复\n{final_response}\n\n"
            "## 检查标准（逐条分析）\n"
            "1. **无幻觉**: 回复中的每个具体数据（温度、时间、风速等）是否都能在搜索结果中找到？\n"
            "2. **时效性**: 搜索结果开头标注了当前时间。回复中的数据时间是否与当前时间差距过大？\n"
            "   - 如果搜索结果数据时间距当前超过3小时，回复是否提到了'信息可能不够及时'？\n"
            "3. **无编造**: 回复是否添加了搜索结果中没有的具体信息（如来源网站名、额外建议等）？\n"
            "4. **相关性**: 回复是否直接回答了用户的问题？\n\n"
            "请先简要分析，然后输出以下 JSON（只输出 JSON，不要其他内容）:\n"
            '{"valid": true或false, "reason": "简短原因", '
            '"suggested_response": "如果不合格，给出修正后的回复；如果合格则留空"}'
        )

        try:
            response = await self.llm_client.chat.completions.create(
                model=get_config().llm.llm_model,
                messages=[{"role": "user", "content": reflection_prompt}],
                temperature=0.0,
                max_tokens=500,
            )
            content = (response.choices[0].message.content or "").strip()

            cleaned = content.replace("```json", "").replace("```", "").strip()
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
            result = json.loads(cleaned)

            if result.get("valid") is True:
                logger.info(f"Search reflection PASSED: {result.get('reason', '')}")
                update["metadata"]["reflection_result"] = "search_passed"
                update["metadata"]["reflection_reason"] = result.get("reason", "")
            else:
                suggested = result.get("suggested_response", "").strip()
                if suggested:
                    logger.warning(
                        f"Search reflection FAILED: {result.get('reason', '')}, "
                        f"applying corrected response"
                    )
                    update["final_response"] = suggested
                    update["metadata"]["reflection_result"] = "search_corrected"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")
                    update["metadata"]["original_response"] = final_response[:200]
                else:
                    logger.warning(
                        f"Search reflection FAILED but no suggestion: {result.get('reason', '')}"
                    )
                    update["metadata"]["reflection_result"] = "search_failed_no_suggestion"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")

        except Exception as e:
            logger.error(f"Search reflection LLM call failed: {e}")
            update["metadata"]["reflection_result"] = "search_error"
            update["metadata"]["reflection_error"] = str(e)

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        update["metadata"]["reflection_latency_ms"] = latency_ms
        logger.info(f"Search reflection done: latency={latency_ms}ms")

        return update

    async def _mainagent_confirm_node(self, state: SupervisorState) -> Dict[str, Any]:
        """【v2.1】主 Agent 确认节点：检查 SubAgent 异常上报，二次确认。

        快通道 (<50ms)：查 Redis 缓存的告警状态。
        - 无告警 → 放行
        - 有告警且 should_block → 拦截结果，返回降级提示
        - 有告警且 action=pass → 放行
        """
        cockpit_id = state.get("cockpit_id", "cockpit-01")

        # 1. 检查是否有未决告警
        try:
            alert = await self.mainagent_confirm.check_before_response(cockpit_id)
        except Exception as e:
            logger.error(f"MainAgent confirm check failed: {e}")
            alert = None

        if alert:
            confirmation = alert.get("mainagent_confirmation", {})
            action = confirmation.get("action", "pass")
            should_block = confirmation.get("should_block", False)

            if should_block or action in ("block", "degrade"):
                # 拦截结果，返回降级提示
                degrade_strategy = confirmation.get("degrade_strategy", "")
                alert_type = alert.get("alert_type", "unknown")
                logger.warning(
                    f"MainAgent blocked response for {cockpit_id}: "
                    f"type={alert_type}, action={action}"
                )
                return {
                    "final_response": (
                        f"系统检测到异常 ({alert_type})，"
                        f"已启动降级模式。请稍后重试。"
                        f"{f' 降级策略: {degrade_strategy}' if degrade_strategy else ''}"
                    ),
                    "metadata": {
                        "blocked_by_mainagent": True,
                        "alert": alert,
                        "mainagent_confirmed": True,
                    },
                }

        # 2. 无异常或确认放行
        return {"metadata": {"mainagent_confirmed": True, "mainagent_passed": True}}

    def _get_system_prompt(self, state: SupervisorState) -> str:
        """根据技能类型选择合适的系统提示词，注入用户画像和记忆。

        v2.1 增强:
            - 注入 user_habits（用户习惯，从 MySQL 加载）
            - 注入 user_profile（用户画像，从 Neo4j 加载）
            - 动态选择 prompt 模板（chat / search / vehicle）

        v2.2.1 修复:
            - 搜索类提示词注入位置状态，无位置时禁止编造地址
            - 闲聊提示词注入位置状态，避免 LLM 基于记忆编造位置
        """
        # v2.2.1: 获取当前位置状态
        location_status = self._get_location_status(state)

        # 搜索类技能使用专用 search 提示词
        if state.get("skill_action") == "web_search" and state.get("search_context"):
            search_prompt = self.prompt_manager.render(
                "search",
                search_context=state.get("search_context", ""),
            )
            if search_prompt:
                # v2.2.1: 追加位置状态约束
                if location_status:
                    search_prompt += f"\n\n## 当前位置状态\n{location_status}\n"
                return search_prompt

        # v2.1: 加载用户画像和习惯
        user_profile = state.get("user_profile", {})
        profile_str = ""
        if user_profile:
            # get_user_profile 返回 {"user_id": "...", "relations": [...]}
            # 需要将 relations 列表格式化为可读文本
            relations = user_profile.get("relations", [])
            if relations:
                profile_str = "; ".join(
                    f"{r.get('relation', '')}: {r.get('target', '')}"
                    for r in relations
                    if r.get("relation") and r.get("target")
                )
            elif user_profile.get("user_id"):
                profile_str = f"用户: {user_profile['user_id']}"

        # v2.1: 从 state 中获取习惯记忆（已在 recall 中加载）
        memory_str = state.get("memory_str", "")
        habits_str = state.get("habits_str", "")

        # 默认使用 chat 提示词（v2.1 增强版）
        prompt = self.prompt_manager.render(
            "chat",
            user_profile=profile_str,
            memory=memory_str,
            user_habits=habits_str,
        )
        if prompt:
            # v2.2.1: 追加位置状态约束
            if location_status:
                prompt += f"\n\n## 当前位置状态\n{location_status}\n"
            return prompt

        # Fallback
        fallback = (
            "你叫小千，是一个智能车载语音助手。"
            f"{profile_str}\n{memory_str}"
        )
        if location_status:
            fallback += f"\n{location_status}"
        return fallback

    def _get_location_status(self, state: SupervisorState) -> str:
        """【v2.2.1】获取当前位置状态，用于注入提示词防止幻觉。

        从车控适配器获取实时位置，如果位置不可用则明确告知 LLM
        不要编造地址信息。
        """
        try:
            adapter = None
            # 尝试从多座舱适配器获取
            cockpit_id = state.get("cockpit_id", "")
            if cockpit_id:
                from nexus.vehicle.factory import get_cockpit_vehicle_adapter
                adapter = get_cockpit_vehicle_adapter(cockpit_id)
            else:
                from nexus.vehicle.factory import build_vehicle_adapter
                adapter = build_vehicle_adapter()

            if adapter and hasattr(adapter, "navigation"):
                nav = adapter.navigation
                loc = nav.get("current_location", "")
                if loc and "未知" not in loc and "不可用" not in loc:
                    return f"用户当前位置：{loc}（可在回复中使用此位置信息）"
                else:
                    return (
                        "⚠️ 当前位置未知（定位服务不可用）。"
                        "禁止在回复中编造或猜测用户的位置信息。"
                        "如果用户询问位置相关问题，请告知定位服务不可用。"
                    )
        except Exception as e:
            logger.debug(f"Failed to get location status: {e}")

        return ""

    async def _generate_llm_response(self, state: SupervisorState) -> str:
        """调用 LLM 生成回复（非流式）。"""
        system_msg = self._get_system_prompt(state)

        # 搜索类技能不需要重复传入 search_ctx（已在 system_msg 中）
        search_ctx = "" if state.get("skill_action") == "web_search" else state.get("search_context", "")

        msgs, new_summary = await self.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=state.get("history", []),
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
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
        system_msg = self._get_system_prompt(state)

        # 搜索类技能不需要重复传入 search_ctx（已在 system_msg 中）
        search_ctx = "" if state.get("skill_action") == "web_search" else state.get("search_context", "")

        msgs, new_summary = await self.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=state.get("history", []),
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
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
        """Reviewer 节点：质量检查 + 记忆存储 + 对话向量化 + 延迟统计。

        v2.1 增强:
            - 记忆提取存储（store_from_text）
            - 对话向量化存储（store_conversation）
            - 两者异步执行，不阻塞响应
        """
        t0 = perf_counter()
        update: Dict[str, Any] = {}

        # 1. 响应质量检查
        final_response = state.get("final_response", "")
        if not final_response or len(final_response.strip()) < 2:
            update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
            update["metadata"] = {"reviewer_fallback": True}

        # 2. 触发后台记忆存储（v2.1: 三重记忆存储）
        if self.memory_manager and final_response:
            user_id = state.get("user_id", "default")
            user_input = state.get("user_input", "")
            cockpit_id = state.get("cockpit_id", "")

            # 2a. 提取记忆三元组 → Milvus + Neo4j
            try:
                self.memory_manager.store_from_text_async(user_input, user_id)
                update.setdefault("metadata", {})["memory_storage_triggered"] = True
            except Exception as e:
                logger.error(f"Memory storage trigger failed: {e}")

            # 2b. v2.1: 对话向量化 → Milvus（语义检索用）
            try:
                self.memory_manager.store_conversation_async(
                    user_input, final_response, user_id, cockpit_id
                )
                update.setdefault("metadata", {})["conversation_vectorized"] = True
            except Exception as e:
                logger.error(f"Conversation vectorization trigger failed: {e}")

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
        config = {}
        if self.checkpoint_saver:
            thread_id = state.get("session_id") or state.get("user_id", "default")
            config = {"configurable": {"thread_id": thread_id}}
        result = await self._graph.ainvoke(state, config=config)
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
            # Reviewer 后台执行，不阻塞
            try:
                asyncio.create_task(self._reviewer_node(state))
            except Exception as e:
                logger.error(f"Background reviewer task failed: {e}")
            return

        # Phase 3: 专家并行执行
        if state.get("active_experts"):
            dispatch_update = await self._dispatch_node(state)
            state.update(dispatch_update)

        # Phase 4: 流式响应
        full_response = ""

        if state.get("skill_handled"):
            # B1: 搜索类技能 → v2.2.2: 先收集完整回复，做反思后统一发送
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                full_response = await self._generate_llm_response(state)
                state["final_response"] = full_response
                # v2.2.2: 搜索类回复也走反思校验
                reflection_update = await self._reflection_node(state)
                if reflection_update.get("final_response"):
                    full_response = reflection_update["final_response"]
                if reflection_update.get("metadata"):
                    state.setdefault("metadata", {}).update(reflection_update["metadata"])
                yield full_response

            # B2: v2.2 工具返回了结构化数据 → Tool→LLM 合成 + 反思
            elif state.get("tool_result") and state.get("tool_result", {}).get("data"):
                full_response = await self._synthesize_tool_response(state)
                state["final_response"] = full_response
                reflection_update = await self._reflection_node(state)
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
            async for chunk in self._stream_llm_response(state):
                full_response += chunk
                yield chunk

        state["final_response"] = full_response

        # 更新历史
        state.setdefault("history", []).extend([
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": full_response},
        ])

        # Phase 5: Reviewer 后台异步执行（不阻塞流式输出）
        try:
            asyncio.create_task(self._reviewer_node(state))
        except Exception as e:
            logger.error(f"Background reviewer task failed: {e}")

    async def stream_with_events(self, state: SupervisorState) -> AsyncGenerator[dict, None]:
        """流式执行工作流，输出结构化事件（v2.0 新增）。

        v2.1 性能优化:
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
        supervisor_update = await self._supervisor_node(state)
        state.update(supervisor_update)

        # 发送意图事件
        intent_name = state.get("intent_source", "")
        yield {"type": "intent", "data": {"intent": intent_name, "source": intent_name}}

        # Phase 2: 澄清分支
        if state.get("need_clarification") and state.get("clarification_prompt"):
            yield {"type": "chunk", "data": {"chunk": state["clarification_prompt"]}}
            state["final_response"] = state["clarification_prompt"]
            # Reviewer 后台执行，不阻塞 done 事件
            asyncio.create_task(self._reviewer_node(state))
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
            # B1: 搜索类技能 → v2.2.2: 先收集完整回复，做反思后统一发送
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                yield {"type": "thinking", "data": {"message": "正在分析搜索结果..."}}
                # 先生成完整回复（不流式）
                full_response = await self._generate_llm_response(state)
                state["final_response"] = full_response
                # v2.2.2: 搜索类回复也走反思校验
                reflection_update = await self._reflection_node(state)
                if reflection_update.get("final_response"):
                    full_response = reflection_update["final_response"]
                # 合并反思 metadata 到 state
                if reflection_update.get("metadata"):
                    state.setdefault("metadata", {}).update(reflection_update["metadata"])
                yield {"type": "chunk", "data": {"chunk": full_response}}

            # B2: v2.2 工具返回了结构化数据 → Tool→LLM 合成 + 反思
            elif state.get("tool_result") and state.get("tool_result", {}).get("data"):
                yield {"type": "thinking", "data": {"message": "正在分析工具结果..."}}
                full_response = await self._synthesize_tool_response(state)
                state["final_response"] = full_response
                reflection_update = await self._reflection_node(state)
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
            async for chunk in self._stream_llm_response(state):
                full_response += chunk
                yield {"type": "chunk", "data": {"chunk": chunk}}

        state["final_response"] = full_response
        state.setdefault("history", []).extend([
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": full_response},
        ])

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
            asyncio.create_task(self._reviewer_node(state))
        except Exception as e:
            logger.error(f"Background reviewer task failed: {e}")
