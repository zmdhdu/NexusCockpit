# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Celery Task Queue — 异步任务队列

本模块负责将耗时操作从主请求链路中剥离，交给 Celery Worker 异步执行。
典型场景包括:
  - 后台记忆存储（task_store_memory）: 将用户对话文本提取记忆后存入图/向量库
  - 过期缓存清理（task_cleanup_cache）: 定期清理语义缓存中的过期条目

架构说明:
  - Broker: RabbitMQ（消息队列，负责任务分发）
  - Backend: Redis（结果存储，使用 db+1 避免与业务缓存冲突）
  - 序列化: JSON（跨语言兼容）
  - 时区: Asia/Shanghai（与业务时区一致）

关键配置:
  - task_time_limit=300: 单任务最大执行时间 5 分钟，超时自动终止
  - task_soft_time_limit=240: 软超时 4 分钟，Worker 可优雅退出
  - worker_prefetch_multiplier=1: 每次只预取 1 个任务，避免长任务阻塞
  - worker_max_tasks_per_child=100: 子进程执行 100 个任务后重启，防止内存泄漏
"""

from __future__ import annotations

from celery import Celery

from nexus.config import get_config

# 创建 Celery 实例
# broker 使用 RabbitMQ，backend 使用 Redis（db+1 与业务缓存隔离）
config = get_config()

celery_app = Celery(
    "nexus_cockpit",
    broker=config.rabbitmq.url,
    backend=f"redis://{config.redis.host}:{config.redis.port}/{config.redis.db + 1}",
)

celery_app.conf.update(
    task_serializer="json",          # 任务参数序列化方式
    accept_content=["json"],         # Worker 接受的内容类型
    result_serializer="json",        # 结果序列化方式
    timezone="Asia/Shanghai",        # 时区设置
    enable_utc=True,                 # 内部使用 UTC 时间戳
    task_track_started=True,         # 任务开始时发送 STARTED 状态
    task_time_limit=300,             # 硬超时: 5 分钟强制终止
    task_soft_time_limit=240,        # 软超时: 4 分钟允许优雅退出
    worker_prefetch_multiplier=1,    # 预取 1 个任务，避免长任务阻塞队列
    worker_max_tasks_per_child=100,  # 子进程执行 100 个任务后重启，防内存泄漏
)


@celery_app.task(name="nexus.tasks.store_memory")
def task_store_memory(user_text: str, user_id: str):
    """后台记忆存储任务。

    从用户对话文本中提取记忆信息，并存入图/向量数据库。
    由于 Celery Worker 运行在同步上下文中，内部通过 asyncio.new_event_loop()
    桥接异步 MemoryManager。

    Args:
        user_text: 用户输入的对话文本
        user_id:   用户唯一标识

    Returns:
        int: 本次存储的记忆条目数量
    """
    import asyncio
    from nexus.memory.manager import MemoryManager

    async def _run():
        manager = MemoryManager()
        manager.connect()
        count = await manager.store_from_text(user_text, user_id)
        manager.close()
        return count

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()


@celery_app.task(name="nexus.tasks.cleanup_cache")
def task_cleanup_cache():
    """清理过期缓存任务。

    定期清理语义缓存（SemanticCache）中的过期条目，释放 Redis 内存。
    通常通过 Celery Beat 定时调度执行。

    Returns:
        int: 本次清理的缓存条目数量
    """
    import asyncio
    from nexus.middleware.redis_cache import SemanticCache

    async def _run():
        cache = SemanticCache()
        await cache.connect()
        count = await cache.clear()
        await cache.close()
        return count

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()
