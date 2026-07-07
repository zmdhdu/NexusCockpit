"""
Initialize Neo4j Constraints and Indexes
运行此脚本创建 Neo4j 约束和索引
用法: python -m scripts.init_neo4j
"""

from __future__ import annotations

import sys

from nexus.core.logger import get_logger, setup_logging
from nexus.rag.graph_store import Neo4jGraphStore

logger = get_logger(__name__)


def main():
    setup_logging()
    logger.info("Initializing Neo4j constraints and indexes...")

    graph_store = Neo4jGraphStore()

    try:
        graph_store.connect()
        logger.info("✅ Neo4j initialized successfully!")
        logger.info("   - Constraint: user_id_unique (User.id)")
        logger.info("   - Index: entity_name_index (Entity.name)")
    except Exception as e:
        logger.error(f"❌ Neo4j initialization failed: {e}")
        sys.exit(1)
    finally:
        graph_store.close()


if __name__ == "__main__":
    main()
