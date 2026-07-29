# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Graph Store Factory — 图谱存储工厂

本地化降级改造后固定使用本地 Neo4j (Docker)。
云端 AuraDB 实现已删除，provider 字段保留向后兼容但忽略 cloud 取值。
"""

from __future__ import annotations

from nexus.core.logger import get_logger
from nexus.rag.graph_base import BaseGraphStore
from nexus.rag.graph_store import Neo4jGraphStore

logger = get_logger(__name__)


def build_graph_store() -> BaseGraphStore:
    """构建图谱存储实例（固定本地 Neo4j）。

    Returns:
        BaseGraphStore 实例 (Neo4jGraphStore)
    """
    logger.info("GraphStore provider: local Neo4j (固定本地)")
    return Neo4jGraphStore()
