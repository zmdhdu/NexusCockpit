# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Graph Store Factory — 图谱存储工厂

根据 .env 的 GRAPH_STORE_PROVIDER 选择图谱后端:
  - local: 本地 Neo4j (Docker)
  - cloud: Neo4j AuraDB (官方云托管)
"""

from __future__ import annotations

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.aura_graph_store import AuraGraphStore
from nexus.rag.graph_base import BaseGraphStore
from nexus.rag.graph_store import Neo4jGraphStore

logger = get_logger(__name__)


def build_graph_store() -> BaseGraphStore:
    """根据 GRAPH_STORE_PROVIDER 配置选择图谱存储后端。

    Returns:
        BaseGraphStore 实例 (Neo4jGraphStore / AuraGraphStore)
    """
    provider = get_config().providers.normalized()["graph_store"]

    if provider == "cloud":
        logger.info("GraphStore provider: Neo4j AuraDB")
        return AuraGraphStore()

    # 默认 local
    logger.info("GraphStore provider: local Neo4j")
    return Neo4jGraphStore()
