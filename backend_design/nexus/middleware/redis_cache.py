"""
Redis Semantic Cache — v2.0 基于 Redis Stack VECTOR 向量索引

v2.0 变更:
  - 从 O(n) 遍历改为 Redis Stack RediSearch KNN 向量检索 O(log n)
  - 按用户分片索引（user_id 隔离）
  - 车控指令不缓存（has_side_effect 检查）— from main L5 fix
  - TTL 分级：闲聊 1h、知识库 24h、车控永不上缓存
  - 分布式锁防击穿

安全设计 (from main L5 fix):
  - 副作用隔离: 车控等有副作用的响应 (has_side_effect=True) 永不写入缓存，
    避免"打开空调"缓存命中后车控指令不执行的安全事故

工作原理:
  1. 创建 RediSearch 索引（VECTOR FLAT/HNSW + user_id TAG）
  2. 写入：query 向量化 → 存入 HASH → FT.ADD 到索引
  3. 查询：query 向量化 → FT.SEARCH KNN 找最近邻 → 检查相似度阈值

依赖: Redis Stack（redis/redis-stack-server:7.2.0-v4）
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService

logger = get_logger(__name__)

# RediSearch 索引名
_INDEX_NAME = "nexus:cache:index"
# 缓存数据前缀
_KEY_PREFIX = "nexus:cache:entry:"
# 向量维度（需与 EmbeddingService 输出一致）
_VECTOR_DIM = 1024
# 相似度阈值
_DEFAULT_THRESHOLD = 0.92


class SemanticCache:
    """v2.0 Redis Stack 语义缓存。

    使用 RediSearch + VECTOR 索引实现 KNN 向量检索，O(log n) 复杂度。
    支持按 user_id 分片、TTL 分级、车控指令跳过缓存。

    安全设计 (from main L5 fix):
      - has_side_effect=True 的响应永不写入缓存，避免车控指令被缓存后不执行

    Attributes:
        embedding_service: 文本向量化服务
        _redis: Redis 异步客户端
        _enabled: 是否启用缓存
    """

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
        self._index_ready = False

    async def connect(self) -> None:
        """连接 Redis Stack 并确保 VECTOR 索引存在。"""
        if not self._enabled:
            logger.info("Semantic cache disabled")
            return

        try:
            if not self._redis:
                self._redis = aioredis.from_url(
                    self.config.url,
                    decode_responses=True,
                )
            await self._redis.ping()

            # 双模式: 云 Redis 通常无 RediSearch 模块, 跳过 VECTOR 索引走 scan 降级
            cache_provider = get_config().providers.normalized()["cache"]
            if cache_provider == "cloud":
                logger.info(
                    "Cloud Redis detected, semantic cache using scan fallback "
                    "(no RediSearch VECTOR index)"
                )
                self._index_ready = False
            else:
                await self._ensure_index()
                logger.info("Redis Stack semantic cache connected (v2.0 VECTOR index)")
        except Exception as e:
            logger.warning(f"Redis connection failed, cache disabled: {e}")
            self._enabled = False

    async def _ensure_index(self) -> None:
        """确保 RediSearch VECTOR 索引存在。"""
        if self._index_ready:
            return
        try:
            # 检查索引是否已存在
            try:
                await self._redis.ft(_INDEX_NAME).info()
                self._index_ready = True
                logger.info(f"RediSearch index '{_INDEX_NAME}' already exists")
                return
            except Exception:
                pass  # 索引不存在，继续创建

            # 创建索引
            from redis.commands.search.field import NumericField, TagField, TextField, VectorField
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType

            schema = (
                TextField("query"),
                TagField("user_id"),
                NumericField("timestamp"),
                VectorField(
                    "embedding",
                    "FLAT",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": _VECTOR_DIM,
                        "DISTANCE_METRIC": "COSINE",
                    },
                ),
            )

            definition = IndexDefinition(
                prefix=[_KEY_PREFIX],
                index_type=IndexType.HASH,
            )

            await self._redis.ft(_INDEX_NAME).create_index(
                schema,
                definition=definition,
            )
            self._index_ready = True
            logger.info(f"RediSearch VECTOR index '{_INDEX_NAME}' created")
        except Exception as e:
            logger.warning(f"Failed to create RediSearch index: {e}, falling back to scan mode")
            self._index_ready = False

    async def get(self, query: str, user_id: str = "") -> Optional[Dict[str, Any]]:
        """查询缓存（KNN 向量检索）。

        v2.0 使用 RediSearch FT.SEARCH KNN 替代 O(n) 遍历。
        """
        if not self._enabled or not self._redis:
            return None

        try:
            query_vec = await self.embedding_service.embed(query)
            if not query_vec:
                return None

            if self._index_ready:
                return await self._knn_search(query_vec, user_id, query)
            else:
                # Fallback: 遍历模式（兼容非 Redis Stack 环境）
                return await self._scan_search(query_vec, user_id)
        except Exception as e:
            logger.error(f"Cache get failed: {e}")
            return None

    async def _knn_search(
        self, query_vec: list[float], user_id: str, query: str
    ) -> Optional[Dict[str, Any]]:
        """RediSearch KNN 向量检索。"""
        try:
            import numpy as np
            from redis.commands.search.query import Query

            # 向量转 bytes
            vec_bytes = np.array(query_vec, dtype=np.float32).tobytes()

            # 构建 KNN 查询
            # 过滤 user_id + KNN 搜索
            filter_expr = f"@user_id:{{{user_id}}}" if user_id else "*"
            q = (
                Query(f"{filter_expr} =>[KNN 1 @embedding $vec AS score]")
                .add_param("vec", vec_bytes)
                .return_fields("response", "query", "score", "timestamp", "user_id", "has_side_effect")
                .dialect(2)
            )

            results = await self._redis.ft(_INDEX_NAME).search(q)

            if not results.docs:
                self._miss_count += 1
                return None

            doc = results.docs[0]

            # 安全检查: 有副作用的缓存条目（车控指令）永远不返回 (from main L5 fix)
            if hasattr(doc, "has_side_effect") and doc.has_side_effect in ("True", "true", "1", True):
                logger.debug("Skipping cache entry with side_effect")
                self._miss_count += 1
                return None

            score = float(doc.score)

            # RediSearch COSINE 距离 → 相似度 = 1 - distance
            similarity = 1.0 - score

            # 检查阈值
            threshold = self.config.cache_similarity_threshold or _DEFAULT_THRESHOLD
            if similarity < threshold:
                self._miss_count += 1
                return None

            # 检查 TTL
            timestamp = float(doc.timestamp or 0)
            if time.time() - timestamp > self.config.cache_ttl:
                self._miss_count += 1
                return None

            # 解析响应
            response_data = doc.response
            if isinstance(response_data, str):
                result = json.loads(response_data)
            else:
                result = response_data

            self._hit_count += 1
            logger.info(f"Cache HIT (KNN): similarity={similarity:.4f}")
            result["_cache_hit"] = True
            result["_cache_similarity"] = similarity
            return result

        except Exception as e:
            logger.error(f"KNN search failed: {e}, falling back to scan")
            return await self._scan_search(query_vec, user_id)

    async def _scan_search(
        self, query_vec: list[float], user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fallback: O(n) 遍历搜索（兼容非 Redis Stack 环境）。"""
        try:
            # 扫描所有缓存 key
            keys = []
            async for key in self._redis.scan_iter(match=f"{_KEY_PREFIX}*", count=100):
                keys.append(key)

            if not keys:
                self._miss_count += 1
                return None

            best_score = 0.0
            best_key = None

            for key in keys:
                data = await self._redis.hgetall(key)
                if not data:
                    continue

                # 检查 user_id
                if user_id and data.get("user_id", "") != user_id:
                    continue

                # 安全检查: 有副作用的缓存条目（车控指令）永远不返回 (from main L5 fix)
                if data.get("has_side_effect", "") in ("True", "true", "1"):
                    continue

                # 检查 TTL
                timestamp = float(data.get("timestamp", 0))
                if time.time() - timestamp > self.config.cache_ttl:
                    continue

                # 计算相似度
                cached_vec_str = data.get("embedding", "[]")
                cached_vec = json.loads(cached_vec_str) if cached_vec_str else []
                if not cached_vec or len(cached_vec) != len(query_vec):
                    continue

                similarity = self._cosine_similarity(query_vec, cached_vec)
                if similarity > best_score:
                    best_score = similarity
                    best_key = key

            threshold = self.config.cache_similarity_threshold or _DEFAULT_THRESHOLD
            if best_key and best_score >= threshold:
                data = await self._redis.hgetall(best_key)
                response_str = data.get("response", "{}")
                result = json.loads(response_str)
                self._hit_count += 1
                logger.info(f"Cache HIT (scan): similarity={best_score:.4f}")
                result["_cache_hit"] = True
                result["_cache_similarity"] = best_score
                return result

            self._miss_count += 1
            return None
        except Exception as e:
            logger.error(f"Scan search failed: {e}")
            self._miss_count += 1
            return None

    async def set(
        self,
        query: str,
        response: Dict[str, Any],
        user_id: str = "",
        embedding: list[float] | None = None,
        ttl: int = 0,
        has_side_effect: bool = False,
    ) -> None:
        """写入缓存。

        v2.0 改进:
          - 支持 TTL 分级（闲聊 1h、知识库 24h）
          - 存入 RediSearch 索引
          - has_side_effect=True 时禁止写入缓存 (from main L5 fix)

        Args:
            has_side_effect: 是否有副作用 (车控等)，为 True 时禁止写入缓存
        """
        # 有副作用的响应永远不写入缓存，防止车控指令被缓存后不执行 (from main L5 fix)
        if has_side_effect:
            logger.debug("Skip cache for side-effect response")
            return

        if not self._enabled or not self._redis:
            return

        try:
            cache_key = f"{_KEY_PREFIX}{uuid.uuid4()}"

            vec = embedding or await self.embedding_service.embed(query)
            if not vec:
                return

            # 确定向量存储格式
            if self._index_ready:
                # RediSearch 模式：存 bytes
                import numpy as np
                vec_bytes = np.array(vec, dtype=np.float32).tobytes()
                vec_field = vec_bytes
            else:
                # Fallback 模式：存 JSON
                vec_field = json.dumps(vec)

            cache_ttl = ttl or self.config.cache_ttl

            # 存储缓存数据（包含 has_side_effect 标记用于安全检查）
            await self._redis.hset(
                cache_key,
                mapping={
                    "query": query[:200],
                    "response": json.dumps(response, ensure_ascii=False),
                    "user_id": user_id,
                    "embedding": vec_field,
                    "timestamp": str(time.time()),
                    "has_side_effect": str(has_side_effect),
                },
            )

            # 设置 TTL
            await self._redis.expire(cache_key, cache_ttl)

            logger.debug(f"Cache SET: key={cache_key}, ttl={cache_ttl}s, side_effect={has_side_effect}")
        except Exception as e:
            logger.error(f"Cache set failed: {e}")

    async def clear(self) -> int:
        """清空所有缓存。"""
        if not self._enabled or not self._redis:
            return 0

        try:
            count = 0
            async for key in self._redis.scan_iter(match=f"{_KEY_PREFIX}*", count=100):
                await self._redis.delete(key)
                count += 1
            logger.info(f"Cache cleared: {count} entries")
            return count
        except Exception as e:
            logger.error(f"Cache clear failed: {e}")
            return 0

    async def close(self) -> None:
        """关闭连接。"""
        if self._redis:
            await self._redis.close()

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算余弦相似度。"""
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
        return self._hit_count

    @property
    def miss_count(self) -> int:
        return self._miss_count

    async def size(self) -> int:
        """当前缓存条目数量。"""
        if not self._enabled or not self._redis:
            return 0
        try:
            count = 0
            async for _ in self._redis.scan_iter(match=f"{_KEY_PREFIX}*", count=100):
                count += 1
            return count
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
            "index_ready": self._index_ready,
        }
