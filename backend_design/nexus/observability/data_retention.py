# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
数据保留策略 — v2.1 自动清理过期数据

按配置的保留天数定期清理 MySQL 表中的旧数据：
- subagent_logs: 保留 30 天
- mainagent_logs: 保留 90 天
- audit_logs: 保留 180 天
- chat_history: 保留 30 天
- llm_cost_tracking: 保留 365 天
- cockpit_stats: 保留 7 天（聚合数据）

清理方式：DELETE 旧数据，可选归档到对象存储。
运行频率：每天凌晨 3:00 执行一次。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

from nexus.core.db_manager import get_db_manager
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 各表的保留策略（天数）
RETENTION_POLICY: Dict[str, int] = {
    "subagent_logs": 30,
    "mainagent_logs": 90,
    "audit_logs": 180,
    "chat_history": 30,
    "llm_cost_tracking": 365,
    "cockpit_stats": 7,
}

# 清理间隔（秒）— 默认 24 小时
CLEANUP_INTERVAL = 86400


class DataRetentionManager:
    """数据保留策略管理器。

    定期清理 MySQL 表中的过期数据，防止数据无限增长。

    Usage:
        manager = DataRetentionManager()
        await manager.start()  # 启动后台清理任务
        await manager.stop()   # 停止
    """

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动后台清理任务。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._cleanup_loop())
        logger.info("Data retention manager started")

    async def stop(self) -> None:
        """停止清理任务。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Data retention manager stopped")

    async def _cleanup_loop(self) -> None:
        """清理循环。"""
        while self._running:
            try:
                await self._run_cleanup()
            except Exception as e:
                logger.error(f"Data retention cleanup error: {e}")

            # 等待下次执行
            await asyncio.sleep(CLEANUP_INTERVAL)

    async def _run_cleanup(self) -> None:
        """执行一次清理。"""
        db = get_db_manager()
        if not db.is_connected:
            logger.debug("MySQL not connected, skipping data retention cleanup")
            return

        total_deleted = 0
        timestamp_col_map = {
            "subagent_logs": "check_time",
            "mainagent_logs": "alert_time",
            "audit_logs": "created_at",
            "chat_history": "created_at",
            "llm_cost_tracking": "created_at",
            "cockpit_stats": "stat_time",
        }

        for table, retention_days in RETENTION_POLICY.items():
            ts_col = timestamp_col_map.get(table, "created_at")
            try:
                rows = await db.execute_query(
                    f"DELETE FROM {table} "
                    f"WHERE {ts_col} < DATE_SUB(NOW(), INTERVAL %s DAY)",
                    (retention_days,),
                )
                # aiomysql doesn't return affected rows for DELETE via execute_query
                # Use a direct count query instead
                count_rows = await db.execute_query(
                    f"SELECT COUNT(*) as cnt FROM {table} "
                    f"WHERE {ts_col} < DATE_SUB(NOW(), INTERVAL %s DAY)",
                    (retention_days,),
                )
                remaining = int(count_rows[0]["cnt"]) if count_rows else 0
                logger.info(
                    f"Data retention: cleaned {table} "
                    f"(retention={retention_days}d, remaining_old={remaining})"
                )
            except Exception as e:
                logger.error(f"Data retention: failed to clean {table}: {e}")

        logger.info(f"Data retention cleanup completed at {datetime.now()}")

    async def get_retention_stats(self) -> Dict[str, Any]:
        """获取各表的数据量和保留策略信息。"""
        db = get_db_manager()
        if not db.is_connected:
            return {}

        stats = {}
        for table, retention_days in RETENTION_POLICY.items():
            try:
                rows = await db.execute_query(
                    f"SELECT COUNT(*) as total, "
                    f"MIN(created_at) as oldest, "
                    f"MAX(created_at) as newest "
                    f"FROM {table}"
                )
                if rows:
                    stats[table] = {
                        "total_rows": int(rows[0].get("total", 0)),
                        "retention_days": retention_days,
                        "oldest_record": str(rows[0].get("oldest", "")),
                        "newest_record": str(rows[0].get("newest", "")),
                    }
            except Exception as e:
                logger.debug(f"Failed to get stats for {table}: {e}")
                stats[table] = {"retention_days": retention_days, "error": str(e)}

        return stats


# 全局单例
_retention_manager: DataRetentionManager | None = None


def get_retention_manager() -> DataRetentionManager:
    """获取数据保留管理器全局单例。"""
    global _retention_manager
    if _retention_manager is None:
        _retention_manager = DataRetentionManager()
    return _retention_manager
