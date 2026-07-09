"""
Initialize Neo4j / AuraDB Constraints and Indexes
运行此脚本创建约束和索引
用法: python -m scripts.init_neo4j
"""

from __future__ import annotations

import sys

from nexus.config import get_config
from nexus.core.logger import get_logger, setup_logging
from nexus.rag.graph_factory import build_graph_store

logger = get_logger(__name__)


def main():
    setup_logging()
    provider = get_config().providers.normalized()["graph_store"]
    logger.info(f"Initializing graph store (provider={provider})...")

    graph_store = build_graph_store()

    try:
        graph_store.connect()
        logger.info("✅ Graph store initialized successfully!")
        logger.info("   - Constraint: user_id_unique (User.id)")
        logger.info("   - Index: entity_name_index (Entity.name)")
    except Exception as e:
        logger.error(f"❌ Graph store initialization failed: {e}")
        sys.exit(1)
    finally:
        graph_store.close()


if __name__ == "__main__":
    main()
