# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reviewer Node — 质量审查节点

从 supervisor_graph.py 的 _reviewer_node() 方法抽取。

职责:
    1. 响应质量检查 — 响应为空或太短时填充备选回复
    2. 记忆存储 — 触发后台异步存储（三元组提取 + 对话向量化）
    3. 延迟统计 — 计算整个流程的总耗时
    4. Agent 活动日志 — 记录到 MySQL subagent_logs

消除循环依赖:
    原实现委托回 SupervisorGraph._reviewer_node()，
    拆分后直接通过 NodeContext 持有 ReviewerAgent 和 MemoryManager 引用。
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from nexus.agent.nodes.context import NodeContext
from nexus.core.logger import get_logger
from nexus.models.state import SupervisorState
from nexus.observability.langfuse import observe

logger = get_logger(__name__)


class ReviewerNode:
    """质量审查节点 — 评分 + 记忆存储 + 延迟统计。

    通过 NodeContext 依赖注入获取共享服务，不持有 SupervisorGraph 引用。

    Args:
        ctx: NodeContext 共享依赖容器
    """

    def __init__(self, ctx: NodeContext):
        self._ctx = ctx

    @observe(name="reviewer-node")
    async def run(self, state: SupervisorState) -> dict[str, Any]:
        """Reviewer 节点：质量检查 + 记忆存储 + 对话向量化 + 延迟统计。

        增强特性:
            - 记忆提取存储（store_from_text）
            - 对话向量化存储（store_conversation）
            - 两者异步执行，不阻塞响应
        """
        ctx = self._ctx
        t0 = perf_counter()
        update: dict[str, Any] = {}

        # 1. 响应质量检查
        final_response = state.get("final_response", "")
        if not final_response or len(final_response.strip()) < 2:
            update["final_response"] = "抱歉，我没有理解你的意思，能再说一次吗？"
            update["metadata"] = {"reviewer_fallback": True}

        # 2. 触发后台记忆存储（三重记忆存储）
        if ctx.memory_manager and final_response:
            user_id = state.get("user_id", "default")
            user_input = state.get("user_input", "")
            cockpit_id = state.get("cockpit_id", "")

            # 2a. 提取记忆三元组 → Milvus + Neo4j
            try:
                ctx.memory_manager.store_from_text_async(user_input, user_id)
                update.setdefault("metadata", {})["memory_storage_triggered"] = True
            except Exception as e:
                logger.error(f"Memory storage trigger failed: {e}")

            # 2b. 对话向量化 → Milvus（语义检索用）
            try:
                ctx.memory_manager.store_conversation_async(
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
