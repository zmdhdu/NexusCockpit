"""
Rate Limiter — 基于 Redis 的分布式限流

使用滑动窗口算法控制每个用户的请求频率。
默认限制: 60 次/分钟。超出限制的请求会被拒绝并返回 429 错误。
"""

from __future__ import annotations

import time
from typing import Optional

import redis.asyncio as aioredis

from nexus.config import get_config
from nexus.core.exceptions import RateLimitError
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Redis 滑动窗口限流器。

    每个用户在指定时间窗口内最多允许 max_requests 次请求。
    使用 Redis Sorted Set 实现滑动窗口。

    Args:
        redis_client: Redis 客户端 (可选)
        max_requests: 窗口内最大请求数 (默认 60)
        window_seconds: 时间窗口大小 (秒，默认 60)
    """

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        max_requests: int = 60,
        window_seconds: int = 60,
    ):
        self.config = get_config().redis
        self._redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def connect(self) -> None:
        """连接 Redis"""
        if self._redis:
            return
        try:
            self._redis = aioredis.from_url(self.config.url, decode_responses=True)
            await self._redis.ping()
            logger.info("RateLimiter connected to Redis")
        except Exception as e:
            logger.warning(f"RateLimiter Redis connection failed: {e}")

    async def check(self, user_id: str, endpoint: str = "default") -> bool:
        """
        检查是否允许请求
        返回 True 表示允许，False 表示被限流
        """
        if not self._redis:
            return True  # Redis 不可用时放行

        key = f"nexus:ratelimit:{user_id}:{endpoint}"
        now = time.time()
        window_start = now - self.window_seconds

        try:
            pipe = self._redis.pipeline()
            # 移除窗口外的记录
            pipe.zremrangebyscore(key, 0, window_start)
            # 添加当前请求
            pipe.zadd(key, {str(now): now})
            # 统计窗口内请求数
            pipe.zcard(key)
            # 设置 key 过期时间
            pipe.expire(key, self.window_seconds)
            results = await pipe.execute()

            count = results[2]
            if count > self.max_requests:
                logger.warning(
                    f"Rate limit exceeded: user={user_id}, endpoint={endpoint}, "
                    f"count={count}/{self.max_requests}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"RateLimit check failed: {e}")
            return True  # 出错时放行

    async def check_or_raise(self, user_id: str, endpoint: str = "default") -> None:
        """检查限流，超出则抛出异常"""
        allowed = await self.check(user_id, endpoint)
        if not allowed:
            raise RateLimitError(
                f"请求频率超限: {self.max_requests}次/{self.window_seconds}秒"
            )

    async def get_remaining(self, user_id: str, endpoint: str = "default") -> int:
        """获取剩余请求次数"""
        if not self._redis:
            return self.max_requests

        key = f"nexus:ratelimit:{user_id}:{endpoint}"
        now = time.time()
        window_start = now - self.window_seconds

        try:
            count = await self._redis.zcount(key, window_start, now)
            return max(0, self.max_requests - count)
        except Exception:
            return self.max_requests

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
