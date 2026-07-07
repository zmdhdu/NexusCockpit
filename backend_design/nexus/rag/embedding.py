"""
Embedding Service — 统一文本向量化服务

将文本转换为高维向量，用于语义搜索和缓存匹配。
支持 Ark API (云端) 调用，内置熔断器和重试机制。

工作原理:
    文本 → Ark API → 2560 维浮点向量 → 用于 Milvus 检索 / Redis 缓存匹配
"""

from __future__ import annotations

import asyncio
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from nexus.config import get_config
from nexus.core.circuit_breaker import CircuitBreaker
from nexus.core.exceptions import LLMError
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """统一 Embedding 服务。

    使用 httpx 异步调用 Ark API 获取文本向量。
    内置 CircuitBreaker 熔断器，连续失败 3 次后自动熔断 15 秒。
    """

    def __init__(self):
        self.config = get_config().llm
        self.client = httpx.AsyncClient(
            base_url=self.config.ark_base_url,
            headers={
                "Authorization": f"Bearer {self.config.ark_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._circuit = CircuitBreaker(name="embedding_api", failure_threshold=3, recovery_period=15.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def embed(self, text: str) -> List[float]:
        """获取单条文本的 embedding 向量。

        Args:
            text: 待向量化的文本

        Returns:
            embedding_dim 维浮点列表，空文本返回零向量

        Raises:
            LLMError: 重试 3 次仍失败时抛出
        """
        if not text or not text.strip():
            return [0.0] * self.config.embedding_dim

        try:
            return await self._circuit.call(self._embed_api, text)
        except Exception as e:
            logger.error(f"Embedding failed after retries: {e}")
            raise LLMError(f"Embedding failed: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """批量获取 embedding，并行处理多个分片。

        Args:
            texts: 文本列表
            batch_size: 每批最大文本数

        Returns:
            向量列表，顺序与输入一致
        """
        if not texts:
            return []

        all_embeddings: List[Optional[List[float]]] = [None] * len(texts)
        batches = [
            (i, texts[i : i + batch_size])
            for i in range(0, len(texts), batch_size)
        ]

        async def process_batch(start_idx: int, batch_texts: List[str]) -> None:
            try:
                result = await self._circuit.call(self._embed_batch_api, batch_texts)
                for j, emb in enumerate(result):
                    all_embeddings[start_idx + j] = emb
            except Exception as e:
                logger.error(f"Batch embedding failed (idx={start_idx}): {e}")
                for j in range(len(batch_texts)):
                    all_embeddings[start_idx + j] = [0.0] * self.config.embedding_dim

        await asyncio.gather(*[process_batch(s, b) for s, b in batches])
        return all_embeddings  # type: ignore

    async def _embed_api(self, text: str) -> List[float]:
        """调用 Ark API 获取 embedding"""
        response = await self.client.post(
            "/embeddings",
            json={
                "model": self.config.embedding_model,
                "input": text,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

    async def _embed_batch_api(self, texts: List[str]) -> List[List[float]]:
        """批量调用 Ark API"""
        response = await self.client.post(
            "/embeddings",
            json={
                "model": self.config.embedding_model,
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]

    async def close(self) -> None:
        await self.client.aclose()
        self._executor.shutdown(wait=False)
