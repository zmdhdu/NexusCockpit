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
    """根据 EMBEDDING_PROVIDER 配置选择 Embedding 后端。"""
    provider = get_config().providers.normalized().get("embedding", "local")

    if provider == "cloud":
        logger.info("Embedding provider: SiliconFlow API (cloud)")
        return EmbeddingService()

    # 默认 local
    logger.info("Embedding provider: local bge-m3 (sentence-transformers)")
    return LocalEmbeddingService()

