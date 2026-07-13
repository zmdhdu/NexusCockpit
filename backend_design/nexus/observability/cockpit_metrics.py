# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
座舱级指标采集 — v2.1 数据中台后端支持

负责采集各座舱的运行指标，写入 Redis 供 SubAgent 巡检，
定时聚合写入 MySQL 供数据中台查询。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

from nexus.core.logger import get_logger
from nexus.core.tenant_context import get_cockpit_id

logger = get_logger(__name__)


class CockpitMetrics:
    """座舱级指标采集器。

    将各座舱的运行指标写入 Redis（实时）和 MySQL（聚合）。
    SubAgent 巡检时从 Redis 读取实时指标。
    数据中台从 MySQL 读取历史聚合数据。

    Attributes:
        redis_client: Redis 客户端
    """

    def __init__(self, redis_client: Optional[aioredis.Redis] = None) -> None:
        self._redis = redis_client

    async def record_chat(self, cockpit_id: str, latency_ms: float, cache_hit: bool) -> None:
        """记录一次对话请求的指标。

        Args:
            cockpit_id: 座舱 ID
            latency_ms: 响应延迟（毫秒）
            cache_hit: 是否命中缓存
        """
        logger.info(f"record_chat called: cockpit_id={cockpit_id}, redis={self._redis is not None}")
        if not self._redis:
            return

        try:
            stats_key = f"{cockpit_id}:stats"
            pipe = self._redis.pipeline()
            pipe.hincrby(stats_key, "chat_count", 1)
            pipe.hincrby(stats_key, "cache_hits" if cache_hit else "cache_misses", 1)
            pipe.hset(stats_key, mapping={
                "last_chat_time": str(time.time()),
                "last_latency_ms": str(latency_ms),
            })
            await pipe.execute()
        except Exception as e:
            logger.error(f"Failed to record chat metrics: {e}")

    async def record_vehicle_cmd(self, cockpit_id: str, success: bool) -> None:
        """记录一次车控指令。

        Args:
            cockpit_id: 座舱 ID
            success: 是否成功
        """
        if not self._redis:
            return

        try:
            stats_key = f"{cockpit_id}:stats"
            pipe = self._redis.pipeline()
            pipe.hincrby(stats_key, "vehicle_cmd_count", 1)
            if not success:
                pipe.hincrby(stats_key, "vehicle_cmd_errors", 1)
            await pipe.execute()
        except Exception as e:
            logger.error(f"Failed to record vehicle cmd metrics: {e}")

    async def record_error(self, cockpit_id: str, error_type: str) -> None:
        """记录一次错误。

        Args:
            cockpit_id: 座舱 ID
            error_type: 错误类型
        """
        if not self._redis:
            return

        try:
            stats_key = f"{cockpit_id}:stats"
            await self._redis.hincrby(stats_key, "error_count", 1)
            await self._redis.hincrby(stats_key, f"error_{error_type}", 1)
        except Exception as e:
            logger.error(f"Failed to record error metrics: {e}")

    async def get_cockpit_stats(self, cockpit_id: str) -> Dict[str, Any]:
        """获取座舱的实时统计指标。

        Args:
            cockpit_id: 座舱 ID

        Returns:
            统计指标字典
        """
        if not self._redis:
            return {}

        try:
            stats_key = f"{cockpit_id}:stats"
            raw = await self._redis.hgetall(stats_key)
            if not raw:
                return {}

            stats: Dict[str, Any] = {}
            for k, v in raw.items():
                if isinstance(k, bytes):
                    k = k.decode()
                if isinstance(v, bytes):
                    v = v.decode()
                try:
                    stats[k] = float(v) if "." in v else int(v)
                except (ValueError, TypeError):
                    stats[k] = v

            # 计算缓存命中率
            hits = stats.get("cache_hits", 0)
            misses = stats.get("cache_misses", 0)
            total = hits + misses
            stats["cache_hit_rate"] = (hits / total) if total > 0 else 0.0

            # 计算错误率
            chat_count = stats.get("chat_count", 1)
            error_count = stats.get("error_count", 0)
            stats["error_rate"] = error_count / chat_count if chat_count > 0 else 0.0

            return stats

        except Exception as e:
            logger.error(f"Failed to get cockpit stats: {e}")
            return {}

    async def get_all_cockpit_stats(self, cockpit_ids: list[str]) -> Dict[str, Dict[str, Any]]:
        """获取所有座舱的统计指标。

        Args:
            cockpit_ids: 座舱 ID 列表

        Returns:
            {cockpit_id: stats_dict}
        """
        result = {}
        for cid in cockpit_ids:
            result[cid] = await self.get_cockpit_stats(cid)
        return result

    async def reset_stats(self, cockpit_id: str) -> None:
        """重置座舱统计（用于测试）。"""
        if not self._redis:
            return
        try:
            await self._redis.delete(f"{cockpit_id}:stats")
        except Exception as e:
            logger.error(f"Failed to reset stats: {e}")


# 全局单例
_metrics: Optional[CockpitMetrics] = None


def get_cockpit_metrics() -> CockpitMetrics:
    """获取座舱指标采集器全局单例。"""
    global _metrics
    if _metrics is None:
        _metrics = CockpitMetrics()
    return _metrics


def set_cockpit_metrics(metrics: CockpitMetrics) -> None:
    """设置全局指标采集器（在 main.py 启动时调用）。"""
    global _metrics
    _metrics = metrics
