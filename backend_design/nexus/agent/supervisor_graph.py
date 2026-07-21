 # Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Supervisor Graph — Multi-Agent 工作流编排核心

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
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

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
from nexus.intent.constants import VEHICLE_INTENT_KEYS
from nexus.intent.router import IntentRouterService
from nexus.memory.manager import MemoryManager
from nexus.models.state import SupervisorState
from nexus.observability.metrics import (
    AGENT_INVOCATIONS,
    AGENT_LATENCY,
    LLM_CALLS,
    LLM_LATENCY,
    RAG_LATENCY,
    RAG_RETRIEVALS,
)
from nexus.prompts import PromptManager
from nexus.skills.registry import SkillRegistry

logger = get_logger(__name__)


class SupervisorGraph:
    """Supervisor 多智能体工作流编排器。

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
        llm_client: AsyncOpenAI | None = None,
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

        # Checkpoint 持久化
        self.checkpoint_saver = checkpoint_saver

        # 后台任务强引用集合（防止 asyncio.Task 被 GC 回收）
        self._background_tasks: set = set()

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
        workflow.add_node("reflection", self._reflection_node)  # 反思校验
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

        # ---- Responder → Reflection → Reviewer → END ----
        workflow.add_edge("responder", "reflection")       # responder → reflection
        workflow.add_edge("reflection", "reviewer")         # reflection → reviewer
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

    async def _supervisor_node(self, state: SupervisorState) -> dict[str, Any]:
        """Supervisor 节点：记忆召回 + 用户画像加载 + 意图路由 + 专家分派决策。

        智能上下文记忆管理:
            - 关键信息提取: 从短期对话历史中提取位置/偏好/身份等关键实体
            - 查询增强: 当用户查询模糊时，用提取的关键信息增强长期记忆召回查询
            - 阈值压缩: 对话轮数超阈值时自动压缩旧对话为滚动摘要

        记忆召回:
            - 使用 GraphRAG 三路融合 + Rerank
            - 加载用户画像（Neo4j）和习惯（MySQL）
            - 习惯记忆注入到 state，供 prompt 使用

        Returns:
            Partial state update
        """
        t0 = perf_counter()
        update: dict[str, Any] = {
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
            "key_context": {},  # 提取的关键上下文
        }

        user_id = state.get("user_id", "default")
        user_input = state.get("user_input", "")
        # 从 state 中获取短期对话历史
        short_term_history = state.get("history", [])  # 对话历史列表 [{role, content}, ...]
        running_summary = state.get("running_summary", "")

        # 关键信息提取 — 从对话历史中提取位置/偏好/身份等关键实体
        # 这是零 LLM 调用的纯正则匹配，不会增加延迟
        key_context = self.responder.compressor.extract_key_context(short_term_history)

        # 如果对话历史中没有提取到位置，从车辆适配器获取 GPS 位置补充
        # 场景: 用户从没说过"我在杭州"，但 GPS 定位在杭州电子科技大学
        if not key_context.get("location"):
            try:
                cockpit_id = state.get("cockpit_id", "")
                adapter = None
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
                        if not key_context:
                            key_context = {}
                        key_context["location"] = loc
            except Exception as e:
                logger.debug(f"Failed to get location from vehicle adapter for key_context: {e}")

        if key_context:
            update["key_context"] = key_context
            logger.info(f"Key context extracted: {key_context}")

        # 阈值压缩 — 对话轮数超阈值时自动压缩旧对话为滚动摘要
        # 这确保长期对话的关键信息不会因 SessionStore 的 20 条截断而丢失
        compressed_history = short_term_history
        new_running_summary = running_summary
        try:
            compressed_history, new_running_summary = (
                await self.responder.compressor.compress_history_with_threshold(
                    short_term_history, running_summary
                )
            )
            if new_running_summary != running_summary:
                update["running_summary"] = new_running_summary
                logger.info(
                    f"Running summary updated: len={len(new_running_summary)}, "
                    f"history_compressed={len(short_term_history)}→{len(compressed_history)} msgs"
                )
            if len(compressed_history) < len(short_term_history):
                # 更新 state 中的历史为压缩后的版本
                # 注意：这里不能直接覆盖 state["history"]，因为 history 是 Annotated[list, add] reducer
                # 压缩后的历史会在后续 build_context 中使用
                update["_compressed_history"] = compressed_history
        except Exception as e:
            logger.error(f"Threshold compression failed, using original history: {e}")

        # 记忆召回 + 用户画像 + 意图路由 并行执行
        # 快速路径: 启发式路由命中的车控指令跳过记忆召回和 RAG，
        # 将 supervisor 延迟从 ~7.5s 降至 <100ms
        quick_intent = self.intent_router.heuristic.route(user_input)
        _is_fast_vehicle = (
            quick_intent
            and any(k in quick_intent for k in VEHICLE_INTENT_KEYS)
        )

        if _is_fast_vehicle:
            # 快速路径: 跳过记忆召回和用户画像加载
            intent = {**self.intent_router._build_default_intent(), **quick_intent, "Route_Source": "heuristic"}
            memories: list[str] = []
            profile: dict[str, Any] = {}
            logger.info("Fast-path: heuristic vehicle command, skipping memory recall")
        else:
            async def _recall_memory():
                """记忆召回：使用查询增强提升长期记忆召回质量。

                通过 extract_key_context + augment_recall_query 增强召回查询，
                核心场景: 用户说"我在杭州"后，问"明天天气如何"时能召回位置记忆。
                """
                try:
                    # 查询增强 — 当用户查询模糊时，从短期记忆补充关键词
                    augmented_query = self.responder.compressor.augment_recall_query(
                        user_input, key_context
                    )

                    # 长期记忆检索（使用增强后的查询）
                    memories = await self.memory_manager.recall(augmented_query, user_id, top_k=3)
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

        # 记录 Prometheus 指标
        AGENT_LATENCY.labels(agent_name="supervisor").observe(latency_ms / 1000)
        AGENT_INVOCATIONS.labels(agent_name="supervisor", status="success").inc()
        # 记忆召回指标
        if memories:
            RAG_RETRIEVALS.labels(source="fusion").inc()
            RAG_LATENCY.observe(latency_ms / 1000)

        logger.info(
            f"Supervisor done: source={update['intent_source']}, "
            f"experts={update['active_experts']}, "
            f"memories={len(update['recalled_memories'])}, "
            f"profile={'yes' if update['user_profile'] else 'no'}, "
            f"clarify={update['need_clarification']}, "
            f"key_ctx={'yes' if update.get('key_context') else 'no'}, "
            f"latency={latency_ms}ms"
        )
        return update

    def _determine_experts(self, intent: dict[str, Any]) -> list[str]:
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
        experts: list[str] = []

        # 车控
        if any(intent.get(k) for k in VEHICLE_INTENT_KEYS):
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

    async def _dispatch_node(self, state: SupervisorState) -> dict[str, Any]:
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
        merged: dict[str, Any] = {"expert_results": []}
        merged_metadata: dict[str, Any] = {}

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
                # 传递 has_side_effect 标记（车控指令禁止缓存）
                if result.get("has_side_effect"):
                    merged["has_side_effect"] = True
                # 传递 tool_result 到顶层 state
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

    async def _responder_node(self, state: SupervisorState) -> dict[str, Any]:
        """Responder 节点：汇总专家输出，生成最终回复。

        增强特性:
            - 分支 B 优化: 当工具返回结构化数据时，将结果回传 LLM 做自然语言合成
            - 不再直接返回原始工具消息，而是经过 LLM 解读后输出
            - 返回 running_summary 确保 LangGraph 持久化滚动摘要
            - 使用压缩后的历史作为 history_update 的基础
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

            # B2: 工具返回了结构化数据 → Tool→LLM 合成
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

        # 更新历史 — 新的一轮追加到压缩后的历史（如果进行了阈值压缩）
        # 这样 SessionStore 保存的就是压缩后的历史 + 新轮次
        history_update = [
            {"role": "user", "content": state.get("user_input", "")},
            {"role": "assistant", "content": full_response},
        ]

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        logger.info(f"Responder done: response_len={len(full_response)}, latency={latency_ms}ms")

        # 返回 running_summary 确保 LangGraph 持久化
        # _generate_llm_response / _synthesize_tool_response 已将新摘要写入 state
        result: dict[str, Any] = {
            "final_response": full_response,
            "history": history_update,
            "metadata": {"responder_latency_ms": latency_ms},
        }
        # 如果有压缩后的历史，返回它以便 LangGraph 更新 state
        compressed = state.get("_compressed_history")
        if compressed is not None:
            result["_compressed_history"] = compressed + history_update
        # 返回更新后的滚动摘要
        running_summary = state.get("running_summary", "")
        if running_summary:
            result["running_summary"] = running_summary

        return result

    async def _synthesize_tool_response(self, state: SupervisorState) -> str:
        """Tool→LLM 合成：将工具调用结果回传 LLM，生成自然语言回复。

        核心思路（CoT 模式）:
            1. 工具返回的结构化数据作为事实依据
            2. LLM 根据用户问题 + 工具结果，推理生成自然回复
            3. 确保回复基于工具真实数据，不编造额外信息

        安全约束:
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

        # 工具返回失败/未知结果时，跳过 LLM 合成，直接返回原始消息
        # 避免 LLM 在“未知位置”基础上编造天气、地址等虚假信息
        failure_indicators = ("未知", "不可用", "失败", "错误", "无法", "不支持")
        if any(indicator in tool_message for indicator in failure_indicators):
            logger.info(
                f"Tool synthesis SKIPPED (failure detected): tool={tool_name}, "
                f"message={tool_message[:80]}"
            )
            return tool_message

        # 构建包含工具结果的系统提示
        # 针对导航类工具增加专门约束，防止编造路线/路况/距离信息
        navigation_constraint = ""
        if "nav" in tool_name.lower() or "navigation" in tool_name.lower():
            navigation_constraint = (
                "\n7. **导航类工具特殊约束（极其重要）**:\n"
                "   - 工具只返回了目的地坐标和名称，**没有路线规划、路况、距离、预计时间等信息**\n"
                "   - **绝对禁止编造**具体路线（如'沿XX路直行'）、路况（如'畅通'）、"
                "距离（如'约5公里'）、预计时间（如'约15分钟'）\n"
                "   - 只需告知用户已开始导航到目的地，并给出目的地名称和坐标即可\n"
                "   - 不要描述沿途 landmarks 或道路名称，除非工具结果中明确包含\n"
            )

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
            "6. 如果工具结果已经是一句完整的话，可以自然地转述即可"
            f"{navigation_constraint}\n"
        )

        # 不注入记忆和习惯，避免 LLM 基于历史记忆编造信息

        # 使用压缩后的历史（如果 supervisor 节点执行了阈值压缩）
        history = state.get("_compressed_history", state.get("history", []))

        # 构建对话上下文
        msgs, new_summary = await self.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=user_input,
            history=history,
            running_summary=state.get("running_summary", ""),
            memory_str="",  # 不注入记忆
            search_ctx="",
        )

        # 保存更新后的滚动摘要到 state
        if new_summary and new_summary != state.get("running_summary", ""):
            state["running_summary"] = new_summary

        try:
            _llm_t0 = perf_counter()
            response = await self.llm_client.chat.completions.create(
                model=get_config().llm.llm_model,
                messages=msgs,
                temperature=0.3,  # 低温度确保事实准确性
                max_tokens=get_config().llm.max_tokens,
            )
            _llm_latency = (perf_counter() - _llm_t0) * 1000
            LLM_CALLS.labels(model=get_config().llm.llm_model, status="success").inc()
            LLM_LATENCY.observe(_llm_latency / 1000)
            synthesized = response.choices[0].message.content.strip()
            logger.info(
                f"Tool synthesis done: tool={tool_name}, "
                f"raw_len={len(tool_message)}, synth_len={len(synthesized)}, "
                f"llm_latency={_llm_latency:.0f}ms"
            )
            return synthesized
        except Exception as e:
            LLM_CALLS.labels(model=get_config().llm.llm_model, status="error").inc()
            logger.error(f"Tool response synthesis failed: {e}, falling back to raw message")
            return tool_message  # 降级：返回原始工具消息

    async def _reflection_node(self, state: SupervisorState) -> dict[str, Any]:
        """反思校验节点：对 LLM 输出做事实性、一致性、无幻觉检查。

        反思策略:
            - 有工具数据时：执行 LLM 反思（CoT 自我批评）
              1. 检查回复是否与工具数据一致（事实性）
              2. 检查回复是否包含编造信息（无幻觉）
              3. 检查回复是否回答了用户问题（相关性）
              4. 不通过时自动修正
            - 有搜索结果时：执行 LLM 反思
              1. 检查回复是否基于搜索结果，无编造
              2. 检查搜索结果时效性是否被正确传达
            - 无工具数据时：轻量检查（非空、长度合理）

        可通过 REFLECTION_ENABLED=false 关闭以减少 LLM 调用。

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

        update: dict[str, Any] = {"metadata": {}}

        # 反思开关 — 关闭时跳过所有 LLM 反思，仅做轻量检查
        if not get_config().llm.reflection_enabled:
            if not final_response or len(final_response.strip()) < 2:
                update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
                update["metadata"]["reflection_result"] = "fallback_empty"
            else:
                update["metadata"]["reflection_result"] = "disabled_by_config"

            # 即使反思禁用，也要做幻觉兜底检查
            # 防止 LLM 编造对话历史（如"您最初是问..."）
            hallucination_fix = self._post_check_chat_response(state, final_response)
            if hallucination_fix is not None:
                update["final_response"] = hallucination_fix
                update["metadata"]["reflection_result"] = "hallucination_guard"

            latency_ms = round((perf_counter() - t0) * 1000, 2)
            update["metadata"]["reflection_latency_ms"] = latency_ms
            logger.info(f"Reflection skipped (disabled by config): latency={latency_ms}ms")
            return update

        # 搜索类回复也做反思校验
        if not tool_result or not tool_result.get("message"):
            if search_context and state.get("skill_action") == "web_search":
                # 搜索类反思：检查回复是否基于搜索结果，是否有时效性问题
                return await self._reflect_search_response(
                    state, user_input, final_response, search_context, t0
                )

            # 通用闲聊反思 — 对所有非工具类回复做 LLM 质量校验（渐进式校验机制）
            # 不再只做轻量检查，而是走完整的 LLM 反思 + retry 流程
            return await self._reflect_chat_response(
                state, user_input, final_response, t0
            )

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

    def _deterministic_date_check(
        self, user_input: str, response: str,
    ) -> str | None:
        """确定性日期校验 — 使用正则表达式检测日期错误，无需 LLM 调用。

        检测场景:
            1. 用户问"明天"，但回复中"明天"后面跟着的日期等于今天的日期
            2. 用户问"后天"，但回复中"后天"后面跟着的日期等于今天或明天的日期
            3. 用户问"今天"，但回复中"今天"后面跟着的日期不等于今天的日期

        Returns:
            如果检测到错误，返回修正后的回复；否则返回 None 表示无问题。
        """
        cn_tz = timezone(timedelta(hours=8))
        now_cn = datetime.now(cn_tz)
        today_str = now_cn.strftime("%m月%d日").lstrip("0").replace("月0", "月")
        tomorrow = now_cn + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%m月%d日").lstrip("0").replace("月0", "月")
        day_after = now_cn + timedelta(days=2)
        day_after_str = day_after.strftime("%m月%d日").lstrip("0").replace("月0", "月")

        # 检测用户是否询问了"明天"或"后天"
        asks_tomorrow = "明天" in user_input or "明日" in user_input
        asks_day_after = "后天" in user_input or "後天" in user_input
        asks_today = "今天" in user_input or "今日" in user_input

        if not (asks_tomorrow or asks_day_after or asks_today):
            return None

        # 提取回复中"明天"后面紧跟的日期（支持 "7月19日" 和 "07月19日" 格式）
        # 匹配模式: "明天" 后面的 50 字符内出现 X月X日
        date_pattern = r"(\d{1,2})月(\d{1,2})日"

        if asks_tomorrow:
            # 找到"明天"后面出现的日期
            for match in re.finditer(r"明天.{0,50}?" + date_pattern, response):
                month, day = int(match.group(1)), int(match.group(2))
                resp_date_str = f"{month}月{day}日"
                if resp_date_str == today_str:
                    # 明天后面跟了今天的日期 → 错误
                    logger.warning(
                        f"Date check FAILED: user asked '明天' but response says "
                        f"'明天{resp_date_str}' (today={today_str}, tomorrow={tomorrow_str})"
                    )
                    # 直接替换错误日期
                    corrected = response.replace(
                        f"明天{resp_date_str}", f"明天{tomorrow_str}"
                    ).replace(
                        f"明天 {resp_date_str}", f"明天 {tomorrow_str}"
                    )
                    # 如果替换后没有变化，尝试更宽泛的替换
                    if corrected == response:
                        corrected = response.replace(resp_date_str, tomorrow_str, 1)
                    return corrected

        if asks_day_after:
            for match in re.finditer(r"后天.{0,50}?" + date_pattern, response):
                month, day = int(match.group(1)), int(match.group(2))
                resp_date_str = f"{month}月{day}日"
                if resp_date_str in (today_str, tomorrow_str):
                    logger.warning(
                        f"Date check FAILED: user asked '后天' but response says "
                        f"'后天{resp_date_str}' (today={today_str}, day_after={day_after_str})"
                    )
                    corrected = response.replace(resp_date_str, day_after_str, 1)
                    return corrected

        return None

    async def _reflect_search_response(
        self, state: SupervisorState, user_input: str,
        final_response: str, search_context: str, t0: float,
    ) -> dict[str, Any]:
        """搜索类回复反思：检查回复是否基于搜索结果，是否正确传达时效性。

        检查项:
            1. 回复中的信息是否都能在搜索结果中找到对应（无幻觉）
            2. 回复是否正确传达了搜索结果的时效性
            3. 回复是否添加了搜索结果中不存在的具体数据（如温度、时间等）
        """
        update: dict[str, Any] = {"metadata": {}}

        # 确定性日期校验（正则，无 LLM 调用，即时完成）
        # 如果检测到日期错误，直接修正并跳过 LLM 反思，大幅减少延迟
        date_fix = self._deterministic_date_check(user_input, final_response)
        if date_fix is not None:
            update["final_response"] = date_fix
            update["metadata"]["reflection_result"] = "date_corrected_deterministic"
            update["metadata"]["reflection_reason"] = "确定性日期校验检测到日期错误，已自动修正"
            update["metadata"]["original_response"] = final_response[:200]
            latency_ms = round((perf_counter() - t0) * 1000, 2)
            update["metadata"]["reflection_latency_ms"] = latency_ms
            logger.info(f"Search reflection: deterministic date check corrected, latency={latency_ms}ms")
            return update

        # 注入当前日期到反思 prompt，防止日期混淆
        cn_tz = timezone(timedelta(hours=8))
        now_cn = datetime.now(cn_tz)
        current_date_str = now_cn.strftime("%Y年%m月%d日 %H:%M")

        # 计算今天/明天的确切日期，注入反思 prompt
        today_str = now_cn.strftime("%m月%d日").lstrip("0").replace("月0", "月")
        tomorrow = now_cn + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%m月%d日").lstrip("0").replace("月0", "月")

        reflection_prompt = (
            "你是一个响应质量审查员。请检查助手的回复是否准确基于搜索结果。\n\n"
            f"## 当前准确时间\n{current_date_str}\n\n"
            f"## 日期对照（绝对准确）\n- 今天: {today_str}\n- 明天: {tomorrow_str}\n\n"
            f"## 用户问题\n{user_input}\n\n"
            f"## 搜索结果（真实数据）\n{search_context[:2000]}\n\n"
            f"## 助手回复\n{final_response}\n\n"
            "## 检查标准（逐条分析）\n"
            "1. **无幻觉**: 回复中的每个具体数据（温度、时间、风速等）是否都能在搜索结果中找到？\n"
            "2. **日期正确性（极其重要）**: 用户问'明天'时，请根据上方的日期对照验证：\n"
            f"   - 今天是 {today_str}，明天是 {tomorrow_str}\n"
            "   - 如果助手回复中的日期与当前日期相同却声称是'明天'，则判定为不合格\n"
            "   - 如果助手回复中的日期是正确的明天日期，则判定为合格\n"
            "3. **时效性**: 搜索结果开头标注了当前时间。回复中的数据时间是否与当前时间差距过大？\n"
            "   - 如果搜索结果数据时间距当前超过3小时，回复是否提到了'信息可能不够及时'？\n"
            "4. **无编造**: 回复是否添加了搜索结果中没有的具体信息（如来源网站名、额外建议等）？\n"
            "5. **相关性**: 回复是否直接回答了用户的问题？\n\n"
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

    async def _reflect_chat_response(
        self, state: SupervisorState, user_input: str,
        final_response: str, t0: float,
    ) -> dict[str, Any]:
        """通用闲聊反思：对所有非工具类回复做 LLM 质量校验。

        反思 prompt 注入完整对话历史，防止反思 LLM 误判"编造对话历史"，
        当用户询问对话历史时，反思 LLM 能对照实际历史记录判断。

        渐进式校验机制（Loop Engineering）:
            1. 首次反思：检查回复的相关性、准确性、一致性、完整性
            2. 如果反思不通过且有修正建议 → 直接采用修正建议
            3. 如果反思不通过但无修正建议 → 带反馈重新生成（最多 1 次重试）
            4. 重试后再次反思，无论结果如何都返回（防止无限循环）

        检查项:
            - 相关性：回复是否直接回答了用户的问题
            - 准确性：回复中是否有明显的 factual error
            - 一致性：回复是否自相矛盾
            - 完整性：回复是否过于简短或遗漏关键信息
            - 无幻觉：回复是否编造了不存在的信息
        """
        update: dict[str, Any] = {"metadata": {}}

        # 注入当前时间，防止时间相关的幻觉
        cn_tz = timezone(timedelta(hours=8))
        now_cn = datetime.now(cn_tz)
        current_date_str = now_cn.strftime("%Y年%m月%d日 %H:%M %A")

        # 如果回复为空或极短，直接返回兜底
        if not final_response or len(final_response.strip()) < 2:
            update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
            update["metadata"]["reflection_result"] = "chat_fallback_empty"
            latency_ms = round((perf_counter() - t0) * 1000, 2)
            update["metadata"]["reflection_latency_ms"] = latency_ms
            return update

        # 提取对话历史，注入反思 prompt，防止反思 LLM 误判"编造对话历史"
        history = state.get("history", [])
        history_str = ""
        if history:
            history_lines = []
            for msg in history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    history_lines.append(f"用户: {content}")
                elif role == "assistant":
                    history_lines.append(f"助手: {content}")
            history_str = "\n".join(history_lines)
        else:
            history_str = "（无历史记录，这是新对话的第一轮）"

        reflection_prompt = (
            "你是一个响应质量审查员。请检查助手的回复是否准确、相关、无幻觉。\n\n"
            f"## 当前准确时间\n{current_date_str}\n\n"
            f"## 当前对话历史（真实记录，用于判断助手是否编造历史）\n{history_str}\n\n"
            f"## 用户问题\n{user_input}\n\n"
            f"## 助手回复\n{final_response}\n\n"
            "## 检查标准（逐条分析）\n"
            "1. **相关性**: 回复是否直接回答了用户的问题？有没有答非所问？\n"
            "2. **准确性**: 回复中是否有明显的 factual error？时间、地点、数据是否正确？\n"
            "3. **一致性**: 回复是否自相矛盾？前后说法是否一致？\n"
            "4. **完整性**: 回复是否过于简短？是否遗漏了用户关心的关键信息？\n"
            "5. **无幻觉**: 回复是否编造了不存在的信息？是否捏造了数据、事件或事实？\n"
            "   ⚠️ **对话历史判断（极其重要）**: 当用户询问对话历史（如'我之前问了什么'、'你还记得吗'）时：\n"
            "   - 请对照上方'当前对话历史'中的真实记录来验证助手回复\n"
            "   - 如果助手回复中提到的历史问题能在对话历史中找到对应，则**不算编造**，判定为合格\n"
            "   - 只有当助手回复中提到的历史在对话历史中**完全找不到对应**时，才判定为编造\n"
            "   - 如果对话历史为空（新对话），但助手声称用户之前问过某些问题，才判定为编造\n\n"
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
                logger.info(f"Chat reflection PASSED: {result.get('reason', '')}")
                update["metadata"]["reflection_result"] = "chat_passed"
                update["metadata"]["reflection_reason"] = result.get("reason", "")
            else:
                suggested = result.get("suggested_response", "").strip()
                if suggested:
                    logger.warning(
                        f"Chat reflection FAILED: {result.get('reason', '')}, "
                        f"applying corrected response"
                    )
                    update["final_response"] = suggested
                    update["metadata"]["reflection_result"] = "chat_corrected"
                    update["metadata"]["reflection_reason"] = result.get("reason", "")
                    update["metadata"]["original_response"] = final_response[:200]
                else:
                    # 反思不通过但没有修正建议 → 带反馈重新生成（最多 1 次）
                    logger.warning(
                        f"Chat reflection FAILED, no suggestion, retrying with feedback: "
                        f"{result.get('reason', '')}"
                    )
                    retry_response = await self._regenerate_with_feedback(
                        state, user_input, final_response, result.get("reason", "")
                    )
                    if retry_response and retry_response != final_response:
                        update["final_response"] = retry_response
                        update["metadata"]["reflection_result"] = "chat_retried"
                        update["metadata"]["reflection_reason"] = result.get("reason", "")
                        update["metadata"]["original_response"] = final_response[:200]
                    else:
                        update["metadata"]["reflection_result"] = "chat_failed_no_suggestion"
                        update["metadata"]["reflection_reason"] = result.get("reason", "")

        except Exception as e:
            logger.error(f"Chat reflection LLM call failed: {e}")
            update["metadata"]["reflection_result"] = "chat_error"
            update["metadata"]["reflection_error"] = str(e)

        latency_ms = round((perf_counter() - t0) * 1000, 2)
        update["metadata"]["reflection_latency_ms"] = latency_ms
        logger.info(f"Chat reflection done: latency={latency_ms}ms")

        return update

    async def _regenerate_with_feedback(
        self, state: SupervisorState, user_input: str,
        original_response: str, feedback: str,
    ) -> str | None:
        """带反思反馈重新生成回复（渐进式校验的 retry 环节）。

        使用压缩后的历史，保存滚动摘要。

        Args:
            state: 当前状态
            user_input: 用户原始输入
            original_response: 首次生成的（有问题的）回复
            feedback: 反思反馈的原因

        Returns:
            重新生成的回复，或 None 表示重试失败
        """
        system_msg = self._get_system_prompt(state)
        search_ctx = "" if state.get("skill_action") == "web_search" else state.get("search_context", "")

        # 使用压缩后的历史
        history = state.get("_compressed_history", state.get("history", []))

        msgs, new_summary = await self.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=user_input,
            history=history,
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
        )

        # 保存滚动摘要
        if new_summary and new_summary != state.get("running_summary", ""):
            state["running_summary"] = new_summary

        # 在对话末尾添加反思反馈，引导 LLM 修正
        msgs.append({
            "role": "assistant",
            "content": original_response,
        })
        msgs.append({
            "role": "user",
            "content": (
                f"【系统校验反馈】你上面的回复存在问题：{feedback}\n"
                "请基于用户最初的问题重新给出一个更准确、更相关的回复。"
                "只输出修正后的回复内容，不要解释。"
            ),
        })

        try:
            response = await self.llm_client.chat.completions.create(
                model=get_config().llm.llm_model,
                messages=msgs,
                temperature=0.5,
                max_tokens=get_config().llm.max_tokens,
            )
            result = response.choices[0].message.content.strip()
            logger.info(f"Regeneration with feedback done, len={len(result)}")
            return result
        except Exception as e:
            logger.error(f"Regeneration with feedback failed: {e}")
            return None

    def _get_system_prompt(self, state: SupervisorState) -> str:
        """根据技能类型选择合适的系统提示词，注入用户画像和记忆。

        增强特性:
            - 注入 key_context（从短期对话历史提取的关键信息：位置/偏好/身份）
            - 这些信息帮助 LLM 理解上下文，如用户之前说了"我在杭州"，
              后续问"明天天气如何"时能自动关联位置
            - 注入 user_habits（用户习惯，从 MySQL 加载）
            - 注入 user_profile（用户画像，从 Neo4j 加载）
            - 动态选择 prompt 模板（chat / search / vehicle）
            - 搜索类提示词注入位置状态，无位置时禁止编造地址
            - 闲聊提示词注入位置状态，避免 LLM 基于记忆编造位置
        """
        # 获取当前位置状态
        location_status = self._get_location_status(state)

        # 注入当前东八区时间，让 LLM 能正确回答时间相关问题
        # 同时计算今天/明天/后天的日期，注入搜索提示词防止日期混淆
        cn_tz = timezone(timedelta(hours=8))
        now_cn = datetime.now(cn_tz)
        weekday_map = {"Monday": "星期一", "Tuesday": "星期二", "Wednesday": "星期三",
                        "Thursday": "星期四", "Friday": "星期五", "Saturday": "星期六",
                        "Sunday": "星期日"}
        weekday_cn = weekday_map.get(now_cn.strftime("%A"), now_cn.strftime("%A"))
        current_time_str = (
            f"{now_cn.strftime('%Y年%m月%d日')} {weekday_cn} "
            f"{now_cn.strftime('%H:%M')}"
        )
        # 计算今天/明天/后天的日期字符串
        today_date_str = now_cn.strftime("%m月%d日")
        tomorrow_date_str = (now_cn + timedelta(days=1)).strftime("%m月%d日")
        day_after_tomorrow_str = (now_cn + timedelta(days=2)).strftime("%m月%d日")

        # 搜索类技能使用专用 search 提示词
        if state.get("skill_action") == "web_search" and state.get("search_context"):
            search_prompt = self.prompt_manager.render(
                "search",
                search_context=state.get("search_context", ""),
                current_time=current_time_str,
                today_date=today_date_str,
                tomorrow_date=tomorrow_date_str,
                day_after_tomorrow_date=day_after_tomorrow_str,
            )
            if search_prompt:
                # 追加位置状态约束
                if location_status:
                    search_prompt += f"\n\n## 当前位置状态\n{location_status}\n"
                return search_prompt

        # 加载用户画像和习惯
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

        # 从 state 中获取习惯记忆（已在 recall 中加载）
        memory_str = state.get("memory_str", "")
        habits_str = state.get("habits_str", "")

        # 注入当前东八区时间，让 LLM 能正确回答时间相关问题
        cn_tz = timezone(timedelta(hours=8))
        now_cn = datetime.now(cn_tz)
        weekday_map = {"Monday": "星期一", "Tuesday": "星期二", "Wednesday": "星期三",
                        "Thursday": "星期四", "Friday": "星期五", "Saturday": "星期六",
                        "Sunday": "星期日"}
        weekday_cn = weekday_map.get(now_cn.strftime("%A"), now_cn.strftime("%A"))
        current_time_str = (
            f"{now_cn.strftime('%Y年%m月%d日')} {weekday_cn} "
            f"{now_cn.strftime('%H:%M')}"
        )

        # 默认使用 chat 提示词
        prompt = self.prompt_manager.render(
            "chat",
            user_profile=profile_str,
            memory=memory_str,
            user_habits=habits_str,
            current_time=current_time_str,
        )
        if prompt:
            # 追加位置状态约束
            if location_status:
                prompt += f"\n\n## 当前位置状态\n{location_status}\n"
            # 注入从短期对话历史提取的关键上下文
            key_ctx = state.get("key_context", {})
            if key_ctx:
                key_ctx_str = self._format_key_context(key_ctx)
                if key_ctx_str:
                    prompt += f"\n\n## 当前对话关键上下文\n{key_ctx_str}\n"
            # 当用户询问对话历史且存在滚动摘要时，引导 LLM 从摘要中查找
            user_input = state.get("user_input", "")
            running_summary = state.get("running_summary", "")
            if running_summary and self._is_history_query(user_input):
                prompt += (
                    "\n\n## 重要指引 — 对话历史查询\n"
                    "上方【历史摘要】包含了之前对话的压缩摘要，其中【对话脉络】部分按时间顺序列出了用户问过的所有问题。\n"
                    "当用户询问\"我之前问了什么\"、\"第一个问题是什么\"等时，请从【历史摘要】的【对话脉络】中查找并回答。\n"
                    "如果摘要中有相关信息，请如实告知；如果摘要中确实没有，才说\"不记得了\"。\n"
                    "绝不能声称\"这是新对话\"或\"没有之前的交流\"，因为【历史摘要】证明之前有过对话。\n"
                )
            return prompt

        # Fallback
        fallback = (
            "你叫小千，是一个智能车载语音助手。"
            f"当前时间: {current_time_str}\n"
            f"{profile_str}\n{memory_str}"
        )
        if location_status:
            fallback += f"\n{location_status}"
        # Fallback 也注入关键上下文
        key_ctx = state.get("key_context", {})
        if key_ctx:
            key_ctx_str = self._format_key_context(key_ctx)
            if key_ctx_str:
                fallback += f"\n{key_ctx_str}"
        return fallback

    @staticmethod
    def _format_key_context(key_context: dict[str, Any]) -> str:
        """格式化关键上下文为可读文本，注入系统提示词。

        将 extract_key_context 提取的字典格式化为 LLM 可理解的自然语言。
        例如: {"location": "杭州", "preferences": ["喜欢咖啡"]}
        → "用户位置：杭州\n用户偏好：喜欢咖啡"

        Args:
            key_context: 关键上下文字典

        Returns:
            格式化后的文本
        """
        if not key_context:
            return ""
        lines = []
        if key_context.get("location"):
            lines.append(f"- 用户提及位置：{key_context['location']}")
        if key_context.get("preferences"):
            prefs = "、".join(key_context["preferences"])
            lines.append(f"- 用户偏好：{prefs}")
        if key_context.get("identity"):
            lines.append(f"- 用户身份：{key_context['identity']}")
        return "\n".join(lines) if lines else ""

    def _get_location_status(self, state: SupervisorState) -> str:
        """获取当前位置状态，用于注入提示词防止幻觉。

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

    # ---- 闲聊预校验 & 幻觉兜底 ----

    # 用户询问对话历史的关键词模式
    _HISTORY_QUERY_PATTERNS = [
        "第一个问题", "第一句话", "第一次问", "刚才问", "之前问",
        "刚才说", "之前说", "上次问", "刚才聊", "之前聊",
        "还记得我", "你还记得", "我说了什么", "我问了什么",
        "我们聊了什么", "对话历史", "聊天记录",
    ]

    # LLM 编造对话历史的可疑模式
    _HALLUCINATED_HISTORY_PATTERNS = [
        "您最初是问", "你最初是问", "您第一次问", "你第一次问",
        "您刚才问的是", "你刚才问的是", "您之前问的是", "你之前问的是",
        "您的第一个问题", "你的第一个问题", "您第一句话", "你第一句话",
    ]

    def _is_history_query(self, user_input: str) -> bool:
        """检测用户是否在询问当前对话的历史记录。"""
        return any(p in user_input for p in self._HISTORY_QUERY_PATTERNS)

    def _has_history(self, state: SupervisorState) -> bool:
        """检查当前对话是否有历史记录（排除当前这一轮）。

        即使对话被阈值压缩，只要 running_summary 存在，
        就说明之前有对话历史（只是被折叠为摘要了）。
        """
        history = state.get("history", [])
        # history 中每轮包含 user + assistant 两条，至少 2 条才算有历史
        if bool(history) and len(history) >= 2:
            return True
        # 如果有滚动摘要，说明之前有对话（被压缩了）
        running_summary = state.get("running_summary", "")
        if running_summary and len(running_summary.strip()) > 0:
            return True
        return False

    def _is_hallucinated_history(self, response: str) -> bool:
        """检测 LLM 回复是否包含编造的对话历史。"""
        return any(p in response for p in self._HALLUCINATED_HISTORY_PATTERNS)

    def _pre_check_chat_response(self, state: SupervisorState) -> str | None:
        """闲聊预校验 — 在调用 LLM 之前拦截明显的问题。

        只有在「既无对话历史」且「无滚动摘要」时才判定为新对话。
        如果有滚动摘要（对话被压缩了），不拦截，让 LLM 基于摘要回答。

        检查场景:
            1. 用户询问对话历史，但当前对话完全无历史且无摘要
               → 直接返回"这是新对话"，不交给 LLM 编造

        Returns:
            如果拦截成功，返回替代回复文本；否则返回 None 表示需要继续调用 LLM。
        """
        user_input = state.get("user_input", "")

        # 场景 1: 用户问对话历史，但当前对话完全没有历史（包括无摘要）
        if self._is_history_query(user_input) and not self._has_history(state):
            logger.info(
                f"Pre-check intercepted: history query with empty history, "
                f"user_input='{user_input[:50]}'"
            )
            return "这是一个新的对话，我们还没有之前的交流记录。请问有什么可以帮您的？"

        return None

    def _post_check_chat_response(self, state: SupervisorState, response: str) -> str | None:
        """闲聊后校验 — 在 LLM 回复返回后、呈现给用户前检查。

        只有在「无历史」且「LLM 编造了历史模式」时才判定为幻觉。
        如果有对话历史，不在此处拦截（交给 LLM 反思校验判断）。

        检查场景:
            1. 当前对话无历史，但 LLM 回复中出现了"您最初是问"等编造历史的模式
               → 覆盖为安全回复

        Returns:
            如果检测到问题，返回修正后的回复；否则返回 None 表示原回复可用。
        """
        user_input = state.get("user_input", "")

        # 场景 1: 无历史但 LLM 编造了对话历史
        # 只有在确实没有历史的情况下，才检查是否编造了历史
        # 如果有对话历史，助手引用历史是合理的，不在此处拦截
        if (not self._has_history(state)
                and self._is_hallucinated_history(response)):
            logger.warning(
                f"Post-check intercepted: hallucinated history detected (no history in state), "
                f"user_input='{user_input[:50]}', response='{response[:80]}'"
            )
            return "这是一个新的对话，我们还没有之前的交流记录。请问有什么可以帮您的？"

        return None

    async def _generate_llm_response(self, state: SupervisorState) -> str:
        """调用 LLM 生成回复（非流式）。

        特性:
            - 使用压缩后的历史（如果 _supervisor_node 执行了阈值压缩）
            - 将 build_context 返回的 new_summary 保存回 state，确保滚动摘要跨轮次持久化
            - 预校验和后校验，防止编造对话历史
        """
        # 预校验 — 拦截明显的问题，不浪费 LLM 调用
        pre_check = self._pre_check_chat_response(state)
        if pre_check is not None:
            return pre_check

        system_msg = self._get_system_prompt(state)

        # 搜索类技能不需要重复传入 search_ctx（已在 system_msg 中）
        search_ctx = "" if state.get("skill_action") == "web_search" else state.get("search_context", "")

        # 使用压缩后的历史（如果 supervisor 节点执行了阈值压缩）
        history = state.get("_compressed_history", state.get("history", []))

        msgs, new_summary = await self.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=history,
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
        )

        # 保存更新后的滚动摘要到 state
        if new_summary and new_summary != state.get("running_summary", ""):
            state["running_summary"] = new_summary

        try:
            _llm_t0 = perf_counter()
            response = await self.llm_client.chat.completions.create(
                model=get_config().llm.llm_model,
                messages=msgs,
                temperature=0.7,
                max_tokens=get_config().llm.max_tokens,
            )
            _llm_latency = (perf_counter() - _llm_t0) * 1000
            LLM_CALLS.labels(model=get_config().llm.llm_model, status="success").inc()
            LLM_LATENCY.observe(_llm_latency / 1000)
            result = response.choices[0].message.content.strip()

            # 后校验 — 检测 LLM 是否编造了对话历史
            post_check = self._post_check_chat_response(state, result)
            if post_check is not None:
                return post_check

            return result
        except Exception as e:
            LLM_CALLS.labels(model=get_config().llm.llm_model, status="error").inc()
            logger.error(f"LLM response failed: {e}")
            return f"抱歉，我遇到了一些问题: {e}"

    async def _stream_llm_response(self, state: SupervisorState) -> AsyncGenerator[str, None]:
        """流式调用 LLM 生成回复。

        使用压缩后的历史，保存滚动摘要。
        增加预校验，如果预校验拦截则直接返回替代回复。
        """
        # 预校验 — 拦截明显的问题，不浪费 LLM 调用
        pre_check = self._pre_check_chat_response(state)
        if pre_check is not None:
            yield pre_check
            return

        system_msg = self._get_system_prompt(state)

        # 搜索类技能不需要重复传入 search_ctx（已在 system_msg 中）
        search_ctx = "" if state.get("skill_action") == "web_search" else state.get("search_context", "")

        # 使用压缩后的历史
        history = state.get("_compressed_history", state.get("history", []))

        msgs, new_summary = await self.responder.compressor.build_context(
            system_prompt=system_msg,
            user_input=state.get("user_input", ""),
            history=history,
            running_summary=state.get("running_summary", ""),
            memory_str=state.get("memory_str", ""),
            search_ctx=search_ctx,
        )

        # 保存滚动摘要
        if new_summary and new_summary != state.get("running_summary", ""):
            state["running_summary"] = new_summary

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

    async def _reviewer_node(self, state: SupervisorState) -> dict[str, Any]:
        """Reviewer 节点：质量检查 + 记忆存储 + 对话向量化 + 延迟统计。

        增强特性:
            - 记忆提取存储（store_from_text）
            - 对话向量化存储（store_conversation）
            - 两者异步执行，不阻塞响应
        """
        t0 = perf_counter()
        update: dict[str, Any] = {}

        # 1. 响应质量检查
        final_response = state.get("final_response", "")
        if not final_response or len(final_response.strip()) < 2:
            update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
            update["metadata"] = {"reviewer_fallback": True}

        # 2. 触发后台记忆存储（三重记忆存储）
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

            # 2b. 对话向量化 → Milvus（语义检索用）
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

        # 记录 Agent 活动到 MySQL subagent_logs（供运营总览引擎活动时间线展示）
        try:
            from nexus.core.db_manager import get_db_manager
            db = get_db_manager()
            if db.is_connected:
                cockpit_id = state.get("cockpit_id", "cockpit-01")
                intent = state.get("intent", {})
                active_experts = state.get("active_experts", [])
                skill_action = state.get("skill_action", "")
                reflection_result = metadata.get("reflection_result", "")

                check_items = {
                    "user_input": state.get("user_input", "")[:100],
                    "intent": intent.get("Intent", ""),
                    "experts": active_experts,
                    "skill_action": skill_action,
                    "reflection": reflection_result,
                    "latency_ms": update["latency_ms"],
                }
                is_anomaly = reflection_result in ("hallucination_guard", "corrected", "failed_no_suggestion")

                await db.insert_subagent_log(
                    cockpit_id=cockpit_id,
                    check_items=check_items,
                    llm_judgment={"reflection": reflection_result, "reason": metadata.get("reflection_reason", "")},
                    decision_trace={"intent_source": intent.get("Route_Source", ""), "experts": active_experts},
                    is_anomaly=is_anomaly,
                )
        except Exception as e:
            logger.warning(f"Failed to log agent activity: {e}")

        logger.info(
            f"Reviewer done: total_latency={update['latency_ms']}ms, "
            f"response='{final_response[:50]}...'"
        )
        return update

    # ---- 公共接口 ----

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
        supervisor_update = await self._supervisor_node(state)
        state.update(supervisor_update)

        # Phase 2: 澄清分支
        if state.get("need_clarification") and state.get("clarification_prompt"):
            yield state["clarification_prompt"]
            state["final_response"] = state["clarification_prompt"]
            # Reviewer 后台执行，不阻塞
            try:
                task = asyncio.create_task(self._reviewer_node(state))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
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
            # B1: 搜索类技能 → 先收集完整回复，做反思后统一发送
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                full_response = await self._generate_llm_response(state)
                state["final_response"] = full_response
                # 搜索类回复也走反思校验
                reflection_update = await self._reflection_node(state)
                if reflection_update.get("final_response"):
                    full_response = reflection_update["final_response"]
                if reflection_update.get("metadata"):
                    state.setdefault("metadata", {}).update(reflection_update["metadata"])
                yield full_response

            # B2: 工具返回了结构化数据 → Tool→LLM 合成 + 反思
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
            # 闲聊回复改为"先生成完整回复 → 渐进式反思校验 → 再发送"
            # 对所有闲聊回复都走 LLM 反思 + retry 流程，确保答案准确后再返回用户
            full_response = await self._generate_llm_response(state)
            state["final_response"] = full_response
            # 通用闲聊反思校验（渐进式校验机制）
            reflection_update = await self._reflection_node(state)
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
            task = asyncio.create_task(self._reviewer_node(state))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception as e:
            logger.error(f"Background reviewer task failed: {e}")

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
            _task = asyncio.create_task(self._reviewer_node(state))
            self._background_tasks.add(_task)
            _task.add_done_callback(self._background_tasks.discard)
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
            # B1: 搜索类技能 → 先收集完整回复，做反思后统一发送
            if state.get("skill_action") == "web_search" and state.get("search_context"):
                yield {"type": "thinking", "data": {"message": "正在分析搜索结果..."}}
                # 先生成完整回复（不流式）
                full_response = await self._generate_llm_response(state)
                state["final_response"] = full_response
                # 搜索类回复也走反思校验
                reflection_update = await self._reflection_node(state)
                if reflection_update.get("final_response"):
                    full_response = reflection_update["final_response"]
                # 合并反思 metadata 到 state
                if reflection_update.get("metadata"):
                    state.setdefault("metadata", {}).update(reflection_update["metadata"])
                yield {"type": "chunk", "data": {"chunk": full_response}}

            # B2: 工具返回了结构化数据 → Tool→LLM 合成 + 反思
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
            # 闲聊回复改为"先生成完整回复 → 渐进式反思校验 → 再发送"
            # 对所有闲聊回复都走 LLM 反思 + retry 流程，确保答案准确后再返回用户
            yield {"type": "thinking", "data": {"message": "正在生成回复..."}}
            full_response = await self._generate_llm_response(state)
            state["final_response"] = full_response
            # 通用闲聊反思校验（渐进式校验机制）
            yield {"type": "thinking", "data": {"message": "正在校验回复质量..."}}
            reflection_update = await self._reflection_node(state)
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
            _task = asyncio.create_task(self._reviewer_node(state))
            self._background_tasks.add(_task)
            _task.add_done_callback(self._background_tasks.discard)
        except Exception as e:
            logger.error(f"Background reviewer task failed: {e}")
