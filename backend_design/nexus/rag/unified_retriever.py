# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Unified Retriever — 统一检索路由层

v2.0 新增模块:
  - 根据 query_type 分发至不同知识库
  - GraphRAG（记忆/习惯）↔ Cherry KB（手册/故障/FAQ）
  - 支持混合检索模式（同时查两个知识库）

路由策略:
  - memory:   查 GraphRAG 用户记忆
  - knowledge: 查 Cherry KB 文档
  - hybrid:   同时查两个知识库，合并结果
  - auto:     自动判断（默认）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from nexus.core.logger import get_logger
from nexus.rag.cherry_kb import CherryKnowledgeBase
from nexus.rag.reranker_base import BaseReranker
from nexus.rag.reranker_factory import build_reranker
from nexus.rag.retriever import GraphRAGRetriever

logger = get_logger(__name__)


class UnifiedRetriever:
    """统一检索路由层。

    根据 query_type 将查询分发到对应的知识库:
        - GraphRAG: 用户记忆、习惯画像、关系网络
        - Cherry KB: 车手册、故障码、FAQ、保养规范
        - Hybrid: 同时查两个，合并结果

    Args:
        graph_rag: GraphRAG 检索器
        cherry_kb: Cherry 知识库
        reranker: Rerank 服务（可选，对混合结果重排）
    """

    def __init__(
        self,
        graph_rag: Optional[GraphRAGRetriever] = None,
        cherry_kb: Optional[CherryKnowledgeBase] = None,
        reranker: Optional[BaseReranker] = None,
    ):
        self.graph_rag = graph_rag or GraphRAGRetriever()
        self.cherry_kb = cherry_kb or CherryKnowledgeBase()
        self.reranker = reranker or build_reranker()

    def connect(self) -> None:
        """连接所有知识库。"""
        self.graph_rag.connect()
        # Cherry KB 的连接由 main.py 传入 milvus_client
        logger.info("Unified retriever connected")

    async def retrieve(
        self,
        query: str,
        user_id: str = "default",
        query_type: str = "auto",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """统一检索入口。

        Args:
            query: 查询文本
            user_id: 用户 ID（记忆检索用）
            query_type: 检索类型 (memory/knowledge/hybrid/auto)
            top_k: 返回前 K 条

        Returns:
            检索结果列表，每项携带 source/score
        """
        if query_type == "auto":
            query_type = self._auto_detect_type(query)

        if query_type == "memory":
            return await self._retrieve_memory(query, user_id, top_k)
        elif query_type == "knowledge":
            return await self._retrieve_knowledge(query, top_k)
        elif query_type == "hybrid":
            return await self._retrieve_hybrid(query, user_id, top_k)
        else:
            return await self._retrieve_memory(query, user_id, top_k)

    def _auto_detect_type(self, query: str) -> str:
        """自动检测查询类型。

        简单规则:
          - 包含"故障码""保养""手册""怎么用"→ knowledge
          - 包含"我喜欢""我的习惯""记得"→ memory
          - 默认 → hybrid
        """
        knowledge_keywords = ("故障", "保养", "手册", "怎么用", "使用方法", "说明", "操作指南")
        memory_keywords = ("我喜欢", "习惯", "记得", "上次", "之前")

        if any(kw in query for kw in knowledge_keywords):
            return "knowledge"
        if any(kw in query for kw in memory_keywords):
            return "memory"
        return "hybrid"

    async def _retrieve_memory(
        self, query: str, user_id: str, top_k: int
    ) -> List[Dict[str, Any]]:
        """检索用户记忆（GraphRAG）。"""
        return await self.graph_rag.retrieve_memories(query, user_id, top_k=top_k)

    async def _retrieve_knowledge(
        self, query: str, top_k: int
    ) -> List[Dict[str, Any]]:
        """检索知识库文档（Cherry KB）。"""
        docs = await self.cherry_kb.search(query, top_k=top_k)
        # 统一格式
        for doc in docs:
            doc.setdefault("source", "knowledge_base")
        return docs

    async def _retrieve_hybrid(
        self, query: str, user_id: str, top_k: int
    ) -> List[Dict[str, Any]]:
        """混合检索（GraphRAG + Cherry KB）。"""
        # 并行检索
        import asyncio
        memory_task = self.graph_rag.retrieve_memories(query, user_id, top_k=top_k)
        kb_task = self.cherry_kb.search(query, top_k=top_k)

        memory_results, kb_results = await asyncio.gather(
            memory_task, kb_task, return_exceptions=True
        )

        # 合并结果
        merged: List[Dict[str, Any]] = []
        if isinstance(memory_results, list):
            for r in memory_results:
                r.setdefault("source", "memory")
                merged.append(r)
        if isinstance(kb_results, list):
            for r in kb_results:
                r.setdefault("source", "knowledge_base")
                merged.append(r)

        # Rerank 合并结果
        if self.reranker and len(merged) > top_k:
            merged = self.reranker.rerank(query, merged, top_k=top_k)

        return merged[:top_k]
