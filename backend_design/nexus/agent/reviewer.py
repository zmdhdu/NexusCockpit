# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reviewer Agent — 质量审查与后处理

Reviewer 是工作流的最后一站，负责:
  1. 质量检查 — 如果响应为空或太短，填充备选回复
  2. 记忆存储 — 触发后台异步存储用户对话记忆
  3. 延迟统计 — 计算整个流程的总耗时
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from nexus.core.logger import get_logger
from nexus.memory.manager import MemoryManager
from nexus.models.state import AgentState

logger = get_logger(__name__)


class ReviewerAgent:
    """审查 Agent: 质量检查 + 后台记忆存储。

    Args:
        memory_manager: 记忆管理器 (可选)，用于存储对话记忆
    """

    def __init__(self, memory_manager: MemoryManager | None = None):
        self.memory_manager = memory_manager

    async def review(self, state: AgentState) -> AgentState:
        """审查并后处理: 质量检查 → 记忆存储 → 延迟统计。

        Args:
            state: 包含 final_response 的 Agent 状态

        Returns:
            更新后的 state，包含 latency_ms 和 metadata
        """
        t0 = perf_counter()

        # 1. 响应质量检查
        if not state.final_response or len(state.final_response.strip()) < 2:
            state.final_response = "抱歉，我没有理解你的意思，能再说一次吗？"
            state.metadata["reviewer_fallback"] = True

        # 2. 触发后台记忆存储 (优先使用 Celery 任务队列，降级为进程内异步)
        if state.final_response:
            try:
                # 尝试通过 Celery 任务队列异步存储 (非阻塞，不阻塞响应)
                from nexus.middleware.task_queue import task_store_memory
                task_store_memory.delay(state.user_input, state.user_id)
                state.metadata["memory_storage_triggered"] = True
                state.metadata["memory_storage_backend"] = "celery"
            except Exception as celery_err:
                # Celery 不可用时降级为进程内异步存储
                logger.debug(f"Celery unavailable, fallback to in-process: {celery_err}")
                if self.memory_manager:
                    try:
                        self.memory_manager.store_from_text_async(
                            state.user_input, state.user_id
                        )
                        state.metadata["memory_storage_triggered"] = True
                        state.metadata["memory_storage_backend"] = "in_process"
                    except Exception as e:
                        logger.error(f"Memory storage trigger failed: {e}")

        # 3. 计算总延迟
        state.metadata["reviewer_latency_ms"] = round((perf_counter() - t0) * 1000, 2)
        total_latency = sum(
            state.metadata.get(k, 0)
            for k in ("planner_latency_ms", "executor_latency_ms", "responder_latency_ms", "reviewer_latency_ms")
        )
        state.latency_ms = round(total_latency, 2)
        state.metadata["total_latency_ms"] = state.latency_ms

        logger.info(
            f"Reviewer done: total_latency={state.latency_ms}ms, "
            f"response='{state.final_response[:50]}...'"
        )
        return state
