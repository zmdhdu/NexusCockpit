"""
Initialize Milvus Collections
运行此脚本创建 Milvus 集合和索引
用法: python -m scripts.init_milvus
"""

from __future__ import annotations

import sys

from nexus.core.logger import get_logger, setup_logging
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_store import MilvusVectorStore

logger = get_logger(__name__)


def main():
    setup_logging()
    logger.info("Initializing Milvus collections...")

    embedding_service = EmbeddingService()
    vector_store = MilvusVectorStore(embedding_service)

    try:
        vector_store.connect()
        logger.info("✅ Milvus collections initialized successfully!")
        logger.info(f"   - Food collection: {vector_store.config.collection_food}")
        logger.info(f"   - Memory collection: {vector_store.config.collection_memory}")
    except Exception as e:
        logger.error(f"❌ Milvus initialization failed: {e}")
        sys.exit(1)
    finally:
        vector_store.disconnect()


if __name__ == "__main__":
    main()
