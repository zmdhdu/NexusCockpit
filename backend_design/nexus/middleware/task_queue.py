"""
Celery Task Queue — 异步任务队列
用于后台记忆存储、日志写入、数据同步等耗时操作
"""

from __future__ import annotations

from celery import Celery

from nexus.config import get_config

# 创建 Celery 实例
config = get_config()

celery_app = Celery(
    "nexus_cockpit",
    broker=config.rabbitmq.url,
    backend=f"redis://{config.redis.host}:{config.redis.port}/{config.redis.db + 1}",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
)


@celery_app.task(name="nexus.tasks.store_memory")
def task_store_memory(user_text: str, user_id: str):
    """后台记忆存储任务"""
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
    """清理过期缓存"""
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
