# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Reminder Scanner — 后台提醒扫描器

作用：定时扫描 Redis Sorted Set 到期提醒，通过 WebSocket 推送通知；
场景：后台定时任务，每 30 秒扫描到期提醒并推送。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

_SCAN_INTERVAL = 30  # 扫描间隔（秒）
_REMINDER_KEY_PREFIX = "nexus:reminders:"


class ReminderScanner:
    """后台提醒扫描器。

    定时扫描 Redis Sorted Set 中的到期提醒并推送通知。

    Attributes:
        _redis: Redis 客户端
        _task: 后台 asyncio 任务
        _running: 是否运行中
    """

    def __init__(self) -> None:
        self._redis: Any = None
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """启动后台扫描任务。"""
        try:
            import redis.asyncio as aioredis
            config = get_config().redis
            self._redis = aioredis.Redis(
                host=config.host,
                port=config.port,
                password=config.password,
                db=config.db,
                decode_responses=True,
            )
            await self._redis.ping()
        except Exception as e:
            logger.warning(f"ReminderScanner: Redis not available, scanner disabled: {e}")
            return

        self._running = True
        self._task = asyncio.create_task(self._scan_loop())
        logger.info(f"ReminderScanner started (interval={_SCAN_INTERVAL}s)")

    async def stop(self) -> None:
        """停止后台扫描任务。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.close()
        logger.info("ReminderScanner stopped")

    async def _scan_loop(self) -> None:
        """后台扫描循环。"""
        while self._running:
            try:
                await self._scan_and_notify()
            except Exception as e:
                logger.error(f"ReminderScanner scan error: {e}")
            await asyncio.sleep(_SCAN_INTERVAL)

    async def _scan_and_notify(self) -> None:
        """扫描到期提醒并推送通知。"""
        if not self._redis:
            return

        now = time.time()
        # 使用 SCAN 遍历所有用户的提醒 key
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match=f"{_REMINDER_KEY_PREFIX}*", count=100
            )
            for key in keys:
                # 获取已到期的提醒
                due_items = await self._redis.zrangebyscore(key, 0, now)
                if not due_items:
                    continue

                user_id = key.replace(_REMINDER_KEY_PREFIX, "")
                for item in due_items:
                    try:
                        data = json.loads(item)
                        content = data.get("content", "")
                        if content:
                            logger.info(
                                f"ReminderScanner: due reminder for user={user_id}: {content}"
                            )
                            # TODO: 通过 WebSocket 推送通知
                            # 当前仅记录日志，后续接入 WebSocket 广播
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"ReminderScanner: invalid reminder data: {e}")

                # 删除已到期的提醒
                await self._redis.zremrangebyscore(key, 0, now)

            if cursor == 0:
                break


# 全局单例
_scanner: ReminderScanner | None = None


def get_reminder_scanner() -> ReminderScanner:
    """获取提醒扫描器全局单例。"""
    global _scanner
    if _scanner is None:
        _scanner = ReminderScanner()
    return _scanner
