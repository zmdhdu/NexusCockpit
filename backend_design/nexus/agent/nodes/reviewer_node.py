# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reviewer Node — 质量审查节点

作用：终审强校验 + 记忆存储 + 对话向量化 + 延迟统计 + Agent活动日志；
场景：五层链路终审关卡，所有对外输出必经此节点校验。
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from nexus.agent.nodes.context import NodeContext
from nexus.agent.output_gateway import validate_output
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
        """Reviewer 节点：终审强校验 + 记忆存储 + 对话向量化 + 延迟统计。

        作为全局唯一出口关卡，所有对外输出内容必须经过终审校验：
            1. 响应质量检查 — 空内容/极短内容填充备选回复
            2. 业务准确性校验 — 车控指令回复必须包含执行状态
            3. 合规性校验 — 通过 Output Gateway 做最终全局校验
            4. 记忆存储 — 触发后台异步存储（三元组提取 + 对话向量化）
            5. 延迟统计 — 计算整个流程的总耗时
            6. Agent 活动日志 — 记录到 MySQL subagent_logs
        """
        ctx = self._ctx
        t0 = perf_counter()
        update: dict[str, Any] = {}

        final_response = state.get("final_response", "")

        # 1. 响应质量检查 — 空内容或极短内容填充备选回复
        if not final_response or len(final_response.strip()) < 2:
            final_response = "抱歉，我没有理解你的意思，能再说一次吗？"
            state["final_response"] = final_response
            update.setdefault("metadata", {})["reviewer_fallback"] = True
            logger.warning("Reviewer: empty/short response, applied fallback")

        # 2. 业务准确性校验 — 车控指令回复必须包含执行状态信息
        skill_action = state.get("skill_action", "")
        if skill_action and skill_action.startswith("vehicle_"):
            expert_results = state.get("expert_results", [])
            has_error = any(
                er.get("skill_status") == "error"
                for er in expert_results
            )
            if has_error:
                failure_indicators = ("失败", "错误", "无法", "不支持", "异常")
                if not any(ind in final_response for ind in failure_indicators):
                    final_response = f"{final_response}\n\n⚠️ 该操作执行时出现异常，请稍后重试或检查车辆状态。"
                    state["final_response"] = final_response
                    update.setdefault("metadata", {})["reviewer_vehicle_error_guard"] = True
                    logger.warning(
                        f"Reviewer: vehicle command '{skill_action}' failed "
                        f"but response didn't mention failure, appended warning"
                    )

        # 3. 合规性校验 — 通过 Output Gateway 做最终全局校验
        reflection_result = state.get("metadata", {}).get("reflection_result", "")
        _skip_reflection_results = (
            "", "chat_fast_skipped", "chat_timeout",
            "search_timeout", "tool_fast_skipped", "tool_timeout",
        )
        reflection_passed = (
            "passed" in reflection_result
            or reflection_result in _skip_reflection_results
        )
        validated, gw_meta = validate_output(
            final_response, state, reflection_passed=reflection_passed
        )
        if validated != final_response:
            final_response = validated
            state["final_response"] = final_response
            logger.info(
                f"Reviewer: output gateway corrected response, reason={gw_meta.get('gateway_reason', '')}"
            )
        update.setdefault("metadata", {}).update(gw_meta)

        # 4. 触发后台记忆存储（三重记忆存储）
        if ctx.memory_manager and final_response:
            user_id = state.get("user_id", "default")
            user_input = state.get("user_input", "")
            cockpit_id = state.get("cockpit_id", "")
            session_id = state.get("session_id", "")

            try:
                ctx.memory_manager.store_from_text_async(user_input, user_id)
                update.setdefault("metadata", {})["memory_storage_triggered"] = True
            except Exception as e:
                logger.error(f"Memory storage trigger failed: {e}")

            try:
                ctx.memory_manager.store_conversation_async(
                    user_input, final_response, user_id, cockpit_id, session_id=session_id
                )
                update.setdefault("metadata", {})["conversation_vectorized"] = True
            except Exception as e:
                logger.error(f"Conversation vectorization trigger failed: {e}")

        # 5. 计算总延迟
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
        for key in metadata:
            if key.endswith("_latency_ms") and key not in (
                "supervisor_latency_ms", "responder_latency_ms", "reviewer_latency_ms"
            ):
                total_latency += metadata[key]

        update["latency_ms"] = round(total_latency, 2)
        update.setdefault("metadata", {})["reviewer_latency_ms"] = reviewer_latency
        update.setdefault("metadata", {})["total_latency_ms"] = update["latency_ms"]

        # 6. 记录 Agent 活动到 MySQL subagent_logs
        try:
            from nexus.core.db_manager import get_db_manager
            db = get_db_manager()
            if db.is_connected:
                cockpit_id = state.get("cockpit_id", "cockpit-01")
                intent = state.get("intent", {})
                active_experts = state.get("active_experts", [])

                check_items = {
                    "user_input": state.get("user_input", "")[:100],
                    "intent": intent.get("Intent", ""),
                    "experts": active_experts,
                    "skill_action": skill_action,
                    "reflection": reflection_result,
                    "latency_ms": update["latency_ms"],
                }
                is_anomaly = reflection_result in (
                    "hallucination_guard", "corrected", "failed_no_suggestion",
                    "chat_corrected", "chat_retried", "search_corrected",
                    "blocked_hallucination", "blocked_sensitive",
                )

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
            f"gateway={gw_meta.get('gateway_result', 'N/A')}, "
            f"response='{final_response[:50]}...'"
        )
        return update
