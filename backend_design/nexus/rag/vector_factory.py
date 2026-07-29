# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Vector Store Factory — 向量存储工厂

本地化降级改造后固定使用本地 Milvus (Docker)。
云端 Zilliz 实现已删除，provider 字段保留向后兼容但忽略 cloud 取值。
"""

from __future__ import annotations

from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_base import BaseVectorStore
from nexus.rag.vector_store import MilvusVectorStore

logger = get_logger(__name__)


def build_vector_store(
    embedding_service: EmbeddingService | None = None,
) -> BaseVectorStore:
    """构建向量存储实例（固定本地 Milvus）。

    Args:
        embedding_service: 文本向量化服务 (可选, 缺省自动创建)

    Returns:
        BaseVectorStore 实例 (MilvusVectorStore)
    """
    logger.info("VectorStore provider: local Milvus (固定本地)")
    return MilvusVectorStore(embedding_service)
