"""
Initialize Milvus / Zilliz Collections
运行此脚本创建向量集合和索引
用法:
    python -m scripts.init_milvus              # 创建集合 (已存在则跳过)
    python -m scripts.init_milvus --rebuild    # 先删除再重建 (切换 embedding 维度时用)
"""

from __future__ import annotations

import sys

from nexus.config import get_config
from nexus.core.logger import get_logger, setup_logging
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_factory import build_vector_store

logger = get_logger(__name__)


def main():
    setup_logging()
    rebuild = "--rebuild" in sys.argv

    provider = get_config().providers.normalized()["vector_store"]
    logger.info(f"Initializing vector store (provider={provider}, rebuild={rebuild})...")

    embedding_service = EmbeddingService()
    vector_store = build_vector_store(embedding_service)

    try:
        if rebuild:
            # 切换 embedding 模型导致维度变化时, 必须先删除旧集合再重建
            cfg = get_config().milvus
            logger.warning(f"Dropping collection '{cfg.collection_food}' for rebuild...")
            vector_store.drop_collection(cfg.collection_food)
            logger.warning(f"Dropping collection '{cfg.collection_memory}' for rebuild...")
            vector_store.drop_collection(cfg.collection_memory)

        vector_store.connect()
        logger.info("✅ Vector store collections initialized successfully!")
        logger.info(f"   - Food collection: {vector_store.config.collection_food}")
        logger.info(f"   - Memory collection: {vector_store.config.collection_memory}")
        logger.info(f"   - Embedding dim: {get_config().llm.embedding_dim}")
    except Exception as e:
        logger.error(f"❌ Vector store initialization failed: {e}")
        sys.exit(1)
    finally:
        vector_store.disconnect()


if __name__ == "__main__":
    main()
