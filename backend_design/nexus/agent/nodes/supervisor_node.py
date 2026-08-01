# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Supervisor Node — 记忆召回 + 意图路由 + 专家分派决策节点

从 supervisor_graph.py 的 _supervisor_node() / _route_from_supervisor() /
_determine_experts() 方法抽取。

职责:
    1. 智能上下文记忆管理（关键信息提取 + 查询增强 + 阈值压缩）
    2. 记忆召回 + 用户画像加载 + 意图路由（并行执行）
    3. 启发式快速路径（车控指令跳过记忆召回，<100ms）
    4. 判断需要哪些专家 → 设置 active_experts
    5. 澄清判断
"""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from nexus.agent.nodes.context import NodeContext
from nexus.core.logger import get_logger
from nexus.intent.constants import VEHICLE_INTENT_KEYS
from nexus.models.state import SupervisorState
from nexus.observability.langfuse import observe
from nexus.observability.metrics import (
    AGENT_INVOCATIONS,
    AGENT_LATENCY,
    RAG_LATENCY,
    RAG_RETRIEVALS,
)

logger = get_logger(__name__)


class SupervisorNode:
    """Supervisor 节点：记忆召回 + 意图路由 + 专家分派决策。

    通过 NodeContext 依赖注入获取共享服务，不持有 SupervisorGraph 引用。

    Args:
        ctx: NodeContext 共享依赖容器
    """

    def __init__(self, ctx: NodeContext):
        self._ctx = ctx

    def route(self, state: SupervisorState) -> str:
        """Supervisor 条件路由：需要分派专家时走 dispatch，否则直连 responder。

        用于 LangGraph add_conditional_edges 的路由函数。
        """
        if state.get("need_clarification"):
            return "responder"
        if not state.get("active_experts"):
            return "responder"
        return "dispatch"

    @observe(name="supervisor-node")
    async def run(self, state: SupervisorState) -> dict[str, Any]:
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
        ctx = self._ctx
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
        key_context = ctx.responder.compressor.extract_key_context(short_term_history)

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
                await ctx.responder.compressor.compress_history_with_threshold(
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
        quick_intent = ctx.intent_router.heuristic.route(user_input)
        _is_fast_vehicle = (
            quick_intent
            and any(k in quick_intent for k in VEHICLE_INTENT_KEYS)
        )

        if _is_fast_vehicle:
            # 快速路径: 跳过记忆召回和用户画像加载
            intent = {**ctx.intent_router._build_default_intent(), **quick_intent, "Route_Source": "heuristic"}
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
                    augmented_query = ctx.responder.compressor.augment_recall_query(
                        user_input, key_context
                    )

                    # 长期记忆检索（使用增强后的查询）
                    memories = await ctx.memory_manager.recall(augmented_query, user_id, top_k=3)
                    return memories
                except Exception as e:
                    logger.error(f"Memory recall failed: {e}")
                    return []

            def _load_profile():
                """加载用户画像"""
                try:
                    return ctx.memory_manager.get_user_profile(user_id) or {}
                except Exception as e:
                    logger.error(f"User profile loading failed: {e}")
                    return {}

            async def _route_intent():
                """意图路由"""
                try:
                    return await ctx.intent_router.route(user_input)
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
          - 搜索/点餐/提醒 → lifestyle
          - 车辆健康诊断 → health
          - 习惯画像/声纹注册 → chat
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

        # 生活推荐（搜索/点餐/提醒）
        if intent.get("Need_Search") or intent.get("Call_elm") or intent.get("Reminder_Action"):
            experts.append("lifestyle")

        # 车辆健康诊断
        if intent.get("Health_Action"):
            experts.append("health")

        # 习惯画像/声纹注册
        if intent.get("Habit_Action") or intent.get("Register_Action"):
            experts.append("chat")

        # 无匹配 → 闲聊兜底
        if not experts:
            experts.append("chat")

        return experts
