"""
Redis Semantic Cache — 基于向量相似度的语义缓存

工作原理:
  1. 用户提问时，先将问题转为 embedding 向量
  2. 在 Redis 中搜索相似的历史查询
  3. 如果相似度超过阈值 (0.92)，直接返回缓存的回答
  4. 否则走完整 Agent 流程，完成后将结果写入缓存

优势: 语义相同的提问 (如"开空调"和"打开冷气")也能命中缓存。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService

logger = get_logger(__name__)


class SemanticCache:
    """Redis 语义缓存。

    使用 Redis Hash 存储缓存条目，使用余弦相似度匹配语义相同/相近的查询。

    Attributes:
        CACHE_PREFIX: 缓存条目 Redis Key 前缀
        INDEX_KEY: 元数据索引 Key
        META_KEY: 元数据 Hash Key (包含 embedding 向量)
    """

    CACHE_PREFIX = "nexus:cache:"
    INDEX_KEY = "nexus:cache:index"
    META_KEY = "nexus:cache:meta"

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        redis_client: Optional[aioredis.Redis] = None,
    ):
        self.config = get_config().redis
        self.embedding_service = embedding_service or EmbeddingService()
        self._redis: Optional[aioredis.Redis] = redis_client
        self._enabled = self.config.cache_enabled
        self._hit_count = 0
        self._miss_count = 0

    async def connect(self) -> None:
        """连接 Redis"""
        if not self._enabled:
            logger.info("Semantic cache disabled")
            return

        try:
            self._redis = aioredis.from_url(
                self.config.url,
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("Redis semantic cache connected")
        except Exception as e:
            logger.warning(f"Redis connection failed, cache disabled: {e}")
            self._enabled = False

    async def get(self, query: str, user_id: str = "") -> Optional[Dict[str, Any]]:
        """
        查询缓存
        返回缓存的响应 dict 或 None
        """
        if not self._enabled or not self._redis:
            return None

        try:
            # 获取查询的 embedding
            query_vec = await self.embedding_service.embed(query)
            if not query_vec:
                return None

            # 在 Redis 中搜索所有缓存向量
            # 使用简单的遍历方式 (适合小规模缓存)
            # 生产环境可使用 Redis Stack 的 VECTOR 类型
            cache_keys = await self._redis.hkeys(self.META_KEY)
            if not cache_keys:
                return None

            best_score = 0.0
            best_key = None

            for key in cache_keys:
                meta_json = await self._redis.hget(self.META_KEY, key)
                if not meta_json:
                    continue
                meta = json.loads(meta_json)

                # 检查 TTL
                if time.time() - meta.get("timestamp", 0) > self.config.cache_ttl:
                    continue

                # 检查 user_id 匹配
                if user_id and meta.get("user_id", "") != user_id:
                    continue

                # 计算余弦相似度
                cached_vec = meta.get("embedding", [])
                if not cached_vec or len(cached_vec) != len(query_vec):
                    continue

                similarity = self._cosine_similarity(query_vec, cached_vec)
                if similarity > best_score:
                    best_score = similarity
                    best_key = key

            if best_key and best_score >= self.config.cache_similarity_threshold:
                # 缓存命中
                cache_data = await self._redis.hget(self.CACHE_PREFIX + best_key, "response")
                if cache_data:
                    self._hit_count += 1
                    logger.info(
                        f"Cache HIT: key={best_key}, similarity={best_score:.4f}"
                    )
                    result = json.loads(cache_data)
                    result["_cache_hit"] = True
                    result["_cache_similarity"] = best_score
                    return result

            self._miss_count += 1
            return None
        except Exception as e:
            logger.error(f"Cache get failed: {e}")
            return None

    async def set(
        self,
        query: str,
        response: Dict[str, Any],
        user_id: str = "",
        embedding: list[float] | None = None,
    ) -> None:
        """写入缓存"""
        if not self._enabled or not self._redis:
            return

        try:
            cache_key = str(uuid.uuid4())

            # 获取 embedding
            vec = embedding or await self.embedding_service.embed(query)
            if not vec:
                return

            # 存储响应数据
            await self._redis.hset(
                self.CACHE_PREFIX + cache_key,
                mapping={"response": json.dumps(response, ensure_ascii=False)},
            )

            # 存储元数据 (包含 embedding 向量)
            meta = {
                "query": query[:200],
                "user_id": user_id,
                "embedding": vec,
                "timestamp": time.time(),
            }
            await self._redis.hset(
                self.META_KEY,
                cache_key,
                json.dumps(meta, ensure_ascii=False),
            )

            # 设置 TTL
            await self._redis.expire(self.CACHE_PREFIX + cache_key, self.config.cache_ttl)
            await self._redis.expire(self.META_KEY, self.config.cache_ttl)

            logger.debug(f"Cache SET: key={cache_key}")
        except Exception as e:
            logger.error(f"Cache set failed: {e}")

    async def clear(self) -> int:
        """清空所有缓存"""
        if not self._enabled or not self._redis:
            return 0

        try:
            # 删除所有缓存条目
            keys = await self._redis.hkeys(self.META_KEY)
            for key in keys:
                await self._redis.delete(self.CACHE_PREFIX + key)
            await self._redis.delete(self.META_KEY)
            logger.info(f"Cache cleared: {len(keys)} entries")
            return len(keys)
        except Exception as e:
            logger.error(f"Cache clear failed: {e}")
            return 0

    async def close(self) -> None:
        """关闭连接"""
        if self._redis:
            await self._redis.close()

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算余弦相似度"""
        if len(a) != len(b) or not a:
            return 0.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    @property
    def is_enabled(self) -> bool:
        return self._enabled and self._redis is not None

    @property
    def hit_count(self) -> int:
        """缓存命中次数"""
        return self._hit_count

    @property
    def miss_count(self) -> int:
        """缓存未命中次数"""
        return self._miss_count

    async def size(self) -> int:
        """当前缓存条目数量"""
        if not self._enabled or not self._redis:
            return 0
        try:
            return await self._redis.hlen(self.META_KEY)
        except Exception:
            return 0

    async def stats(self) -> Dict[str, Any]:
        """返回缓存统计信息。"""
        total = self._hit_count + self._miss_count
        hit_rate = round(self._hit_count / total * 100, 1) if total > 0 else 0
        return {
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": hit_rate,
            "size": await self.size(),
        }
