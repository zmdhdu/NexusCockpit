# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Embedding Service — 统一文本向量化服务

框架替换: 使用 langchain_openai.OpenAIEmbeddings 替代手写 httpx + CircuitBreaker + tenacity。
OpenAIEmbeddings 自带连接池管理、自动重试(max_retries=3)、异步支持、批量向量化。

接口保持不变，7 个调用方（vector_store/retriever/cherry_kb/redis_cache 等）无需修改。
"""

from __future__ import annotations

from nexus.config import get_config
from nexus.core.exceptions import LLMError
from nexus.core.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """统一 Embedding 服务（框架委托实现）。

    内部使用 langchain_openai.OpenAIEmbeddings，替代手写 httpx+CircuitBreaker+retry。
    接口: embed() / embed_batch() / embed_async() / close() 保持不变。
    """

    def __init__(self):
        self.config = get_config().llm
        from nexus.rag.framework_adapters import get_langchain_embeddings
        self._embeddings = get_langchain_embeddings()
        self._closed = False

    async def embed(self, text: str) -> list[float]:
        """获取单条文本的 embedding 向量。"""
        if self._closed or not text or not text.strip():
            return [0.0] * self.config.embedding_dim
        try:
            return await self._embeddings.aembed_query(text)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise LLMError(f"Embedding failed: {e}")

    async def embed_async(self, text: str) -> list[float]:
        """异步 embedding（embed 的别名，与 LocalEmbeddingService 接口对齐）。"""
        return await self.embed(text)

    async def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """批量获取 embedding。"""
        if self._closed or not texts:
            return [] if not texts else [[0.0] * self.config.embedding_dim] * len(texts)
        try:
            return await self._embeddings.aembed_documents(texts)
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            return [[0.0] * self.config.embedding_dim] * len(texts)

    async def close(self) -> None:
        """释放资源。"""
        self._closed = True
