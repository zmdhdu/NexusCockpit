"""
Rate Limiter — 基于 Redis 的分布式限流

使用 Redis Lua 脚本实现原子性滑动窗口算法，保证:
  1. 原子性: 清理旧条目 + 添加新条目 + 计数在同一个 Redis 操作中完成
  2. 无污染: 超限请求不会添加到计数中，避免合法请求被误拒
  3. 分布式安全: 多实例并发下不会出现竞态条件

默认限制: 60 次/分钟。超出限制的请求会被拒绝并抛出 RateLimitError (429)。
"""

from __future__ import annotations

import time
from typing import Optional

import redis.asyncio as aioredis

from nexus.config import get_config
from nexus.core.exceptions import RateLimitError
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# Lua 脚本: 原子性滑动窗口限流
# ============================================================
# 参数:
#   KEYS[1] = 限流 key (如 nexus:ratelimit:user1:chat)
#   ARGV[1] = 当前时间戳 (秒)
#   ARGV[2] = 窗口起始时间 (now - window_seconds)
#   ARGV[3] = 最大请求数
#   ARGV[4] = 窗口大小 (秒，用于设置 key 过期)
# 返回:
#   1 = 允许通过
#   0 = 被限流
_RATE_LIMIT_LUA = """
-- 清理窗口外的旧记录
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[2])

-- 统计当前窗口内请求数
local count = redis.call('ZCARD', KEYS[1])

-- 如果已超限，直接拒绝 (不添加到计数，避免污染)
if tonumber(count) >= tonumber(ARGV[3]) then
    return 0
end

-- 未超限，添加当前请求
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[1])

-- 设置 key 过期时间 (窗口大小的 2 倍，确保旧条目被清理)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4]) * 2)

return 1
"""


class RateLimiter:
    """Redis 原子滑动窗口限流器。

    使用 Lua 脚本保证 ZREMRANGEBYSCORE + ZADD + ZCARD 的原子性，
    并在超限时跳过 ZADD，避免超限请求污染计数器。

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
        self._lua_script: Optional[str] = None

    async def connect(self) -> None:
        """连接 Redis 并加载 Lua 脚本"""
        if self._redis:
            return
        try:
            self._redis = aioredis.from_url(self.config.url, decode_responses=True)
            await self._redis.ping()
            # 预加载 Lua 脚本 (SCRIPT LOAD)，后续用 EVALSHA 调用更高效
            self._lua_script = await self._redis.script_load(_RATE_LIMIT_LUA)
            logger.info("RateLimiter connected to Redis (Lua script loaded)")
        except Exception as e:
            logger.warning(f"RateLimiter Redis connection failed: {e}")

    async def check(self, user_id: str, endpoint: str = "default") -> bool:
        """
        检查是否允许请求 (原子性操作)。
        返回 True 表示允许，False 表示被限流。

        超限请求不会写入计数器，避免污染后续合法请求的判断。
        """
        if not self._redis:
            return True  # Redis 不可用时放行

        key = f"nexus:ratelimit:{user_id}:{endpoint}"
        now = time.time()
        window_start = now - self.window_seconds

        try:
            # 优先使用 EVALSHA (预加载的脚本)，失败则降级为 EVAL
            if self._lua_script:
                result = await self._redis.evalsha(
                    self._lua_script,
                    1,
                    key,
                    str(now),
                    str(window_start),
                    str(self.max_requests),
                    str(self.window_seconds),
                )
            else:
                result = await self._redis.eval(
                    _RATE_LIMIT_LUA,
                    1,
                    key,
                    str(now),
                    str(window_start),
                    str(self.max_requests),
                    str(self.window_seconds),
                )

            if result == 0:
                logger.warning(
                    f"Rate limit exceeded: user={user_id}, endpoint={endpoint}, "
                    f"limit={self.max_requests}/{self.window_seconds}s"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"RateLimit check failed: {e}")
            return True  # 出错时放行 (降级策略)

    async def check_or_raise(self, user_id: str, endpoint: str = "default") -> None:
        """检查限流，超出则抛出 RateLimitError (会被全局处理器映射为 429)"""
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
