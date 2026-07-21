# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Task Queue — 异步任务队列

使用 asyncio.create_task() 进程内异步执行，无需额外中间件。

优势:
  - 无需额外中间件（RabbitMQ）
  - 无需启动 Worker 进程
  - 部署更简单，适合车载场景
  - 延迟更低（无队列转发开销）

注意:
  - 进程内异步任务在进程重启时会丢失（可接受，记忆存储有重试机制）
  - 不支持分布式任务调度（单机模式足够）
"""

from __future__ import annotations

import asyncio

from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 后台任务强引用集合（防止 asyncio.Task 被 GC 回收）
_background_tasks: set[asyncio.Task] = set()


def create_background_task(coro, name: str = "") -> asyncio.Task:
    """创建后台异步任务，自动管理强引用。

    替代传统消息队列的 delay() 调用，实现进程内异步执行。

    Args:
        coro: 协程对象
        name: 任务名称（用于日志）

    Returns:
        asyncio.Task 对象
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    logger.debug(f"Background task created: {name or coro}")
    return task


async def store_memory_async(user_text: str, user_id: str) -> int:
    """异步记忆存储任务。

    在后台异步执行记忆提取和存储，不阻塞主对话流程。

    Args:
        user_text: 用户输入的对话文本
        user_id: 用户唯一标识

    Returns:
        本次存储的记忆条目数量
    """
    from nexus.memory.manager import MemoryManager

    try:
        manager = MemoryManager()
        manager.connect()
        count = await manager.store_from_text(user_text, user_id)
        manager.close()
        logger.info(f"Memory stored: user={user_id}, count={count}")
        return count
    except Exception as e:
        logger.error(f"Memory storage failed: {e}")
        return 0
