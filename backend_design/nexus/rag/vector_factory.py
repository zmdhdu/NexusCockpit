# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Vector Store Factory — 向量存储工厂

根据 .env 的 VECTOR_STORE_PROVIDER 选择向量库后端:
  - local: 本地 Milvus (Docker)
  - cloud: Zilliz Cloud (Milvus 官方云托管)
"""

from __future__ import annotations

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_base import BaseVectorStore
from nexus.rag.vector_store import MilvusVectorStore
from nexus.rag.zilliz_vector_store import ZillizVectorStore

logger = get_logger(__name__)


def build_vector_store(
    embedding_service: EmbeddingService | None = None,
) -> BaseVectorStore:
    """根据 VECTOR_STORE_PROVIDER 配置选择向量存储后端。

    Args:
        embedding_service: 文本向量化服务 (可选, 缺省自动创建)

    Returns:
        BaseVectorStore 实例 (MilvusVectorStore / ZillizVectorStore)
    """
    provider = get_config().providers.normalized()["vector_store"]

    if provider == "cloud":
        logger.info("VectorStore provider: Zilliz Cloud")
        return ZillizVectorStore(embedding_service)

    # 默认 local
    logger.info("VectorStore provider: local Milvus")
    return MilvusVectorStore(embedding_service)
