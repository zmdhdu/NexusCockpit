# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Generation Task Pool — AI 生成任务独立托管池

底层修复: 原实现 SSE 连接直接绑定 Agent pipeline 执行，
客户端断连（页面切换/组件卸载）即中断 pipeline，导致生成内容丢失。

现改为: pipeline 在后台 asyncio.Task 中独立运行，事件写入缓冲队列，
SSE endpoint 从队列读取事件。客户端断连仅停止读取，不终止 pipeline。
客户端重连后可查询任务状态并获取已生成内容。

设计要点:
    1. pipeline 生命周期脱离 SSE 连接，由 task_pool 统一管理
    2. 事件缓冲队列 (asyncio.Queue) 解耦生产者(pipeline)和消费者(SSE)
    3. 任务完成后保留最终结果，客户端可查询
    4. 仅用户主动调用 cancel_task() 才终止 pipeline
    5. 自动清理过期任务，防止内存泄漏
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from nexus.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GenerationTask:
    """单个生成任务的状态容器。

    Attributes:
        task_id: 唯一任务 ID
        session_id: 会话 ID
        user_id: 用户 ID
        state: SupervisorState（pipeline 执行完毕后包含最终结果）
        events: 已产生的事件列表（缓冲）
        event_queue: 事件队列（SSE 消费者从此读取）
        asyncio_task: 后台 asyncio.Task 引用
        status: pending / running / completed / failed / cancelled
        created_at: 创建时间戳
        completed_at: 完成时间戳
        final_response: 最终回复文本
        error: 错误信息
    """
    task_id: str
    session_id: str
    user_id: str
    state: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    event_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    asyncio_task: asyncio.Task | None = None
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    final_response: str = ""
    error: str = ""


class GenerationTaskPool:
    """AI 生成任务独立托管池。

    管理 pipeline 的完整生命周期，脱离 SSE 连接：
        - submit(): 提交生成任务，返回 task_id
        - consume_events(): SSE endpoint 从此读取事件流
        - get_task(): 查询任务状态和结果
        - cancel_task(): 用户主动取消生成
        - cleanup_expired(): 清理过期任务

    使用方式:
        pool = GenerationTaskPool(agent_graph)
        task_id = await pool.submit(state)
        async for event in pool.consume_events(task_id):
            yield event  # SSE 推送
    """

    # 过期清理间隔（秒）— 任务完成后保留 5 分钟供客户端查询
    _EXPIRE_SECONDS = 300
    # 最大并发任务数
    _MAX_CONCURRENT = 20

    def __init__(self, agent_graph: Any):
        """初始化任务池。

        Args:
            agent_graph: SupervisorGraph 实例（需实现 stream_with_events 方法）
        """
        self._agent_graph = agent_graph
        self._tasks: dict[str, GenerationTask] = {}
        self._cleanup_task: asyncio.Task | None = None

    def start_cleanup_loop(self) -> None:
        """启动后台清理循环（在 FastAPI startup 事件中调用）。"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("GenerationTaskPool cleanup loop started")

    def stop_cleanup_loop(self) -> None:
        """停止后台清理循环（在 FastAPI shutdown 事件中调用）。"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("GenerationTaskPool cleanup loop stopped")

    async def submit(self, state: dict[str, Any]) -> str:
        """提交生成任务到后台执行。

        Args:
            state: SupervisorState 字典

        Returns:
            task_id: 任务唯一 ID
        """
        # 并发限制
        running = sum(1 for t in self._tasks.values() if t.status == "running")
        if running >= self._MAX_CONCURRENT:
            raise RuntimeError(f"Task pool full: {running}/{self._MAX_CONCURRENT} concurrent tasks")

        task_id = f"gen_{uuid.uuid4().hex[:16]}"
        session_id = state.get("session_id", "")
        user_id = state.get("user_id", "")

        gen_task = GenerationTask(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            state=state,
        )

        # 创建后台 asyncio.Task 执行 pipeline
        gen_task.asyncio_task = asyncio.create_task(self._run_pipeline(gen_task))
        gen_task.status = "running"
        self._tasks[task_id] = gen_task

        logger.info(f"GenerationTask submitted: task_id={task_id}, session={session_id}")
        return task_id

    async def _run_pipeline(self, gen_task: GenerationTask) -> None:
        """后台执行 Agent pipeline，事件写入队列和列表。

        pipeline 独立于 SSE 连接运行：
            - 正常完成: status=completed，final_response 写入
            - 异常: status=failed，error 写入
            - 用户取消: status=cancelled
        """
        try:
            async for event in self._agent_graph.stream_with_events(gen_task.state):
                # 写入事件缓冲（列表 + 队列）
                gen_task.events.append(event)
                await gen_task.event_queue.put(event)

                # 捕获 done 事件中的最终回复
                if event.get("type") == "done":
                    gen_task.final_response = event.get("data", {}).get("response", "")

            gen_task.status = "completed"
            gen_task.completed_at = time.time()
            logger.info(
                f"GenerationTask completed: task_id={gen_task.task_id}, "
                f"events={len(gen_task.events)}, "
                f"response_len={len(gen_task.final_response)}"
            )

        except asyncio.CancelledError:
            gen_task.status = "cancelled"
            gen_task.completed_at = time.time()
            logger.info(f"GenerationTask cancelled by user: task_id={gen_task.task_id}")

        except Exception as e:
            gen_task.status = "failed"
            gen_task.error = str(e)
            gen_task.completed_at = time.time()
            logger.error(f"GenerationTask failed: task_id={gen_task.task_id}, error={e}")
            # 将错误事件写入队列，供 SSE 消费者接收
            error_event = {
                "type": "error",
                "data": {"message": f"生成失败: {e}"},
            }
            gen_task.events.append(error_event)
            await gen_task.event_queue.put(error_event)

    async def consume_events(self, task_id: str) -> Any:
        """SSE endpoint 从此方法读取事件流。

        如果任务已完成且队列中有未消费的事件，先消费完再结束。
        如果任务正在运行，阻塞等待新事件。

        Args:
            task_id: 任务 ID

        Yields:
            事件字典
        """
        gen_task = self._tasks.get(task_id)
        if gen_task is None:
            yield {"type": "error", "data": {"message": "任务不存在或已过期"}}
            return

        while True:
            try:
                # 设置超时避免永久阻塞
                event = await asyncio.wait_for(gen_task.event_queue.get(), timeout=0.5)
                yield event
                if event.get("type") == "done" or event.get("type") == "error":
                    return
            except asyncio.TimeoutError:
                # 检查任务是否已完成
                if gen_task.status in ("completed", "failed", "cancelled"):
                    # 任务已完成，检查是否有剩余事件
                    if gen_task.event_queue.empty():
                        # 如果任务完成但没有 done 事件（如被取消），发送一个 done 事件
                        if gen_task.status == "cancelled":
                            yield {"type": "done", "data": {
                                "response": gen_task.final_response or "（已停止生成）",
                                "latency_ms": 0,
                            }}
                        elif gen_task.status == "failed":
                            yield {"type": "done", "data": {
                                "response": f"生成失败: {gen_task.error}",
                                "latency_ms": 0,
                            }}
                        return
                continue

    def get_task(self, task_id: str) -> GenerationTask | None:
        """查询任务状态和结果。

        客户端重连后可调用此方法获取已生成的内容。
        """
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """用户主动取消生成任务。

        仅用户点击【暂停生成】按钮时调用此方法。
        页面切换/组件卸载不会调用此方法，任务继续运行。

        Returns:
            True 如果任务被成功取消，False 如果任务不存在或已完成
        """
        gen_task = self._tasks.get(task_id)
        if gen_task is None:
            return False
        if gen_task.status != "running":
            return False
        if gen_task.asyncio_task and not gen_task.asyncio_task.done():
            gen_task.asyncio_task.cancel()
            return True
        return False

    async def _cleanup_loop(self) -> None:
        """后台清理循环 — 定期清理过期任务。"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    def cleanup_expired(self) -> int:
        """清理过期任务。

        删除已完成超过 _EXPIRE_SECONDS 秒的任务。

        Returns:
            清理的任务数量
        """
        now = time.time()
        expired_ids = [
            tid for tid, task in self._tasks.items()
            if task.status in ("completed", "failed", "cancelled")
            and task.completed_at > 0
            and (now - task.completed_at) > self._EXPIRE_SECONDS
        ]
        for tid in expired_ids:
            del self._tasks[tid]
        if expired_ids:
            logger.info(f"GenerationTaskPool cleaned up {len(expired_ids)} expired tasks")
        return len(expired_ids)

    def get_stats(self) -> dict[str, Any]:
        """获取任务池统计信息。"""
        total = len(self._tasks)
        running = sum(1 for t in self._tasks.values() if t.status == "running")
        completed = sum(1 for t in self._tasks.values() if t.status == "completed")
        failed = sum(1 for t in self._tasks.values() if t.status == "failed")
        return {
            "total": total,
            "running": running,
            "completed": completed,
            "failed": failed,
            "max_concurrent": self._MAX_CONCURRENT,
        }
