# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

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


# ============================================================
# Lua 脚本: 原子性令牌桶限流 (Phase 5: 分布式令牌桶)
# ============================================================
# 令牌桶算法特点:
#   - 允许突发流量 (桶满时一次性消耗多个令牌)
#   - 平均速率受令牌生成速率控制
#   - 适合 LLM API 调用限流 (突发 + 稳定速率)
#
# 参数:
#   KEYS[1] = 令牌桶 key (如 nexus:tokenbucket:user1:chat)
#   ARGV[1] = 当前时间戳 (秒，浮点)
#   ARGV[2] = 桶容量 (burst)
#   ARGV[3] = 令牌生成速率 (tokens/秒)
#   ARGV[4] = 请求消耗的令牌数 (通常为 1)
# 返回:
#   1 = 允许通过 (有足够令牌)
#   0 = 被限流 (令牌不足)
_TOKEN_BUCKET_LUA = """
-- 获取当前桶状态: [剩余令牌数, 上次补充时间]
local bucket = redis.call('HMGET', KEYS[1], 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

-- 初始化桶 (首次请求)
if tokens == nil then
    tokens = tonumber(ARGV[2])  -- 桶满
    last_refill = tonumber(ARGV[1])
end

-- 计算需要补充的令牌 (基于时间差)
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local rate = tonumber(ARGV[3])
local elapsed = math.max(0, now - last_refill)
local refill = elapsed * rate

-- 补充令牌 (不超过容量)
tokens = math.min(capacity, tokens + refill)

-- 检查是否有足够令牌
local needed = tonumber(ARGV[4])
if tokens >= needed then
    tokens = tokens - needed
    redis.call('HMSET', KEYS[1], 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', KEYS[1], 3600)  -- 1小时过期
    return 1
else
    -- 令牌不足，更新最后补充时间但不消耗令牌
    redis.call('HMSET', KEYS[1], 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', KEYS[1], 3600)
    return 0
end
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
        redis_client: aioredis.Redis | None = None,
        max_requests: int = 60,
        window_seconds: int = 60,
    ):
        self.config = get_config().redis
        self._redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lua_script: str | None = None
        self._token_bucket_script: str | None = None

    async def connect(self) -> None:
        """连接 Redis 并加载 Lua 脚本"""
        if self._redis:
            return
        try:
            self._redis = aioredis.from_url(self.config.url, decode_responses=True)
            await self._redis.ping()
            # 预加载 Lua 脚本 (SCRIPT LOAD)，后续用 EVALSHA 调用更高效
            self._lua_script = await self._redis.script_load(_RATE_LIMIT_LUA)
            self._token_bucket_script = await self._redis.script_load(_TOKEN_BUCKET_LUA)
            logger.info("RateLimiter connected to Redis (Lua scripts loaded: sliding window + token bucket)")
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

    async def check_token_bucket(
        self,
        user_id: str,
        endpoint: str = "default",
        capacity: int = 10,
        rate: float = 1.0,
        cost: int = 1,
    ) -> bool:
        """令牌桶限流检查 (Phase 5: 分布式令牌桶)。

        与滑动窗口不同，令牌桶允许突发流量:
          - 桶容量 (capacity) 控制最大突发量
          - 生成速率 (rate) 控制平均速率
          - 每次请求消耗 cost 个令牌

        适用场景: LLM API 调用限流
          (允许短时间内集中调用，但长期速率受限)

        Args:
            user_id: 用户 ID
            endpoint: 接口标识
            capacity: 桶容量 (最大突发量)
            rate: 令牌生成速率 (tokens/秒)
            cost: 请求消耗的令牌数

        Returns:
            True 表示允许，False 表示被限流
        """
        if not self._redis:
            return True  # Redis 不可用时放行

        key = f"nexus:tokenbucket:{user_id}:{endpoint}"
        now = time.time()

        try:
            if self._token_bucket_script:
                result = await self._redis.evalsha(
                    self._token_bucket_script,
                    1,
                    key,
                    str(now),
                    str(capacity),
                    str(rate),
                    str(cost),
                )
            else:
                result = await self._redis.eval(
                    _TOKEN_BUCKET_LUA,
                    1,
                    key,
                    str(now),
                    str(capacity),
                    str(rate),
                    str(cost),
                )

            if result == 0:
                logger.warning(
                    f"Token bucket rate limit exceeded: user={user_id}, "
                    f"endpoint={endpoint}, capacity={capacity}, rate={rate}/s"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Token bucket check failed: {e}")
            return True  # 出错时放行 (降级策略)

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
