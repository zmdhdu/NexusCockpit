# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Embedding Factory — 向量化服务工厂

框架优先策略:
  1. 优先使用 langchain_openai.OpenAIEmbeddings（自带连接池+重试+回调）
  2. 降级使用手写 LocalEmbeddingService (sentence-transformers)

配置:
  EMBEDDING_PROVIDER=local  (默认, 本地 bge-m3)
  EMBEDDING_PROVIDER=cloud  (云端硅基流动 API)
"""

from __future__ import annotations

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService
from nexus.rag.local_embedding import LocalEmbeddingService

logger = get_logger(__name__)


def build_embedding_service() -> EmbeddingService | LocalEmbeddingService:
    """根据 EMBEDDING_PROVIDER 配置选择 Embedding 后端。

    根据 EMBEDDING_PROVIDER 配置选择 Embedding 后端。
    """
    provider = get_config().providers.normalized().get("embedding", "local")

    if provider == "cloud":
        logger.info("Embedding provider: SiliconFlow API (cloud)")
        return EmbeddingService()

    # 默认 local
    logger.info("Embedding provider: local bge-m3 (sentence-transformers)")
    return LocalEmbeddingService()


def get_langchain_embeddings():
    """获取 LangChain OpenAIEmbeddings 实例（推荐）。

    替代手写 EmbeddingService (144行)。
    自带连接池管理 + 自动重试 + 异步支持 + 批量向量化。

    使用方式:
        from nexus.rag.embedding_factory import get_langchain_embeddings
        embeddings = get_langchain_embeddings()
        vec = await embeddings.aembed_query("你好")
        vecs = await embeddings.aembed_documents(["文本1", "文本2"])

    Returns:
        OpenAIEmbeddings 实例
    """
    from nexus.rag.framework_adapters import get_langchain_embeddings as _get
    return _get()
