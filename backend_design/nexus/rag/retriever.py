# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
GraphRAG Retriever — 融合向量检索、图谱检索、BM25 全文检索

核心特性:
  - 三路混合检索（向量+图谱+BM25）
  - Rerank 后处理：bge-reranker-v2-m3 对 Top-20 重排至 Top-5
  - 引用溯源：每条结果携带 source/score 字段
  - RRF 三路融合

检索策略:
  - 向量路: Milvus 语义相似度召回（基于文本含义匹配）
  - 图谱路: Neo4j 关系遍历召回（基于实体关系匹配）
  - BM25路: 全文关键词匹配召回（基于词频精确匹配）
  - 融合策略: RRF (Reciprocal Rank Fusion) 三路融合
  - 后处理: Rerank 模型重排 Top-N
"""

from __future__ import annotations

from typing import Any

from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService
from nexus.rag.graph_factory import build_graph_store
from nexus.rag.graph_store import Neo4jGraphStore
from nexus.rag.reranker_base import BaseReranker
from nexus.rag.reranker_factory import build_reranker
from nexus.rag.vector_base import BaseVectorStore
from nexus.rag.vector_factory import build_vector_store

logger = get_logger(__name__)


class GraphRAGRetriever:
    """GraphRAG 三路融合检索器。

    三路召回 + RRF 融合 + Rerank 重排:
        - 向量路: Milvus 语义相似度召回
        - 图谱路: Neo4j 关系遍历召回
        - BM25路: 全文关键词匹配召回
        - 融合策略: RRF (Reciprocal Rank Fusion) 排序
        - 后处理: bge-reranker-v2-m3 Rerank 重排

    Args:
        vector_store: Milvus 向量存储
        graph_store: Neo4j 图谱存储
        embedding_service: 文本向量化服务
        reranker: Rerank 服务（可选，自动初始化）
        enable_rerank: 是否启用 Rerank
        enable_bm25: 是否启用 BM25
    """

    def __init__(
        self,
        vector_store: BaseVectorStore | None = None,
        graph_store: Neo4jGraphStore | None = None,
        embedding_service: EmbeddingService | None = None,
        reranker: BaseReranker | None = None,
        enable_rerank: bool = True,
        enable_bm25: bool = True,
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or build_vector_store(self.embedding_service)
        self.graph_store = graph_store or build_graph_store()
        self.enable_rerank = enable_rerank
        self.enable_bm25 = enable_bm25

        # Rerank 服务 (由工厂按 provider 选择)
        self.reranker = reranker or (build_reranker() if enable_rerank else None)

        # BM25 索引（延迟初始化）
        self._bm25 = None
        self._bm25_docs: list[str] = []

    def connect(self) -> None:
        """连接所有存储"""
        self.vector_store.connect()
        self.graph_store.connect()
        logger.info("GraphRAG retriever initialized (BM25 + Rerank)")

    def _init_bm25(self, documents: list[str]) -> None:
        """初始化 BM25 索引。"""
        if not self.enable_bm25 or not documents:
            return
        try:
            from rank_bm25 import BM25Okapi
            # 简单分词：按空格和中文字符切分
            tokenized = [self._tokenize(doc) for doc in documents]
            self._bm25 = BM25Okapi(tokenized)
            self._bm25_docs = documents
            logger.info(f"BM25 index initialized with {len(documents)} docs")
        except ImportError:
            logger.warning("rank-bm25 not installed, BM25 retrieval disabled")
            self.enable_bm25 = False
        except Exception as e:
            logger.error(f"BM25 init failed: {e}")
            self.enable_bm25 = False

    def _tokenize(self, text: str) -> list[str]:
        """中文分词：优先使用 jieba 分词，降级为按字切分；英文按空格切分。"""
        import re
        # 英文按空格
        tokens = re.findall(r"[a-zA-Z]+", text.lower())
        # 中文分词：优先 jieba
        try:
            import jieba
            chinese_text = "".join(re.findall(r"[\u4e00-\u9fff]+", text))
            if chinese_text:
                tokens.extend(jieba.lcut(chinese_text))
        except ImportError:
            # 降级：按字切分
            tokens.extend(re.findall(r"[\u4e00-\u9fff]", text))
        return [t for t in tokens if t.strip()]

    def _bm25_search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """BM25 全文检索。"""
        if not self._bm25 or not self._bm25_docs:
            return []
        try:
            tokenized_query = self._tokenize(query)
            scores = self._bm25.get_scores(tokenized_query)
            # 取 Top-K
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
            results = []
            for idx in top_indices:
                if scores[idx] > 0:
                    results.append({
                        "text": self._bm25_docs[idx],
                        "score": float(scores[idx]),
                        "source": "bm25",
                    })
            return results
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    async def retrieve_memories(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        graph_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """三路融合检索用户记忆。

        流程:
            1. 向量路召回 Top-(top_k*2)
            2. 图谱路召回
            3. BM25 路召回（如有索引）
            4. RRF 三路融合
            5. Rerank 重排 Top-20 → Top-K

        Returns:
            去重排序后的记忆列表，每项携带 source/score
        """
        # 向量路召回
        vec_results = await self.vector_store.search_memory(query, user_id, top_k=top_k * 4)

        # 图谱路召回
        graph_results = self.graph_store.search_user_graph(user_id, depth=graph_depth)

        # BM25 路召回（需要先有文档索引）
        bm25_results: list[dict[str, Any]] = []
        if self.enable_bm25 and self._bm25:
            bm25_results = self._bm25_search(query, top_k=top_k * 2)

        # RRF 融合排序
        fused = self._rrf_fuse(vec_results, graph_results, bm25_results)

        # Rerank 重排
        if self.reranker and len(fused) > top_k:
            fused = self.reranker.rerank(query, fused, top_k=top_k)

        return fused[:top_k]

    async def retrieve_food(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索食材库。"""
        vec_results = await self.vector_store.search_food(query, top_k=top_k)
        graph_match = self.graph_store.search_food(query)

        if graph_match and not any(
            r.get("item_name") == graph_match for r in vec_results
        ):
            vec_results.insert(0, {"item_name": graph_match, "score": 1.0, "source": "graph"})

        return vec_results[:top_k]

    def _rrf_fuse(
        self,
        vec_results: list[dict[str, Any]],
        graph_results: list[str],
        bm25_results: list[dict[str, Any]] = None,
        k: int = 60,
    ) -> list[dict[str, Any]]:
        """RRF (Reciprocal Rank Fusion) 三路融合排序。

        公式: RRF(d) = Σ 1/(k + rank_i(d))
        三路: 向量路、图谱路、BM25路

        Args:
            vec_results: 向量路召回结果
            graph_results: 图谱路召回结果 (文本列表)
            bm25_results: BM25 路召回结果
            k: 平滑常数

        Returns:
            融合排序后的结果列表
        """
        scores: dict[str, float] = {}
        texts: dict[str, dict[str, Any]] = {}

        # 向量路打分
        for rank, item in enumerate(vec_results):
            text = item.get("text", "")
            if not text:
                continue
            scores[text] = scores.get(text, 0) + 1.0 / (k + rank + 1)
            texts[text] = {**item, "source": "vector", "rrf_score": 0}

        # 图谱路打分
        for rank, text in enumerate(graph_results):
            scores[text] = scores.get(text, 0) + 1.0 / (k + rank + 1)
            if text not in texts:
                texts[text] = {"text": text, "source": "graph", "rrf_score": 0}

        # BM25 路打分
        if bm25_results:
            for rank, item in enumerate(bm25_results):
                text = item.get("text", "")
                if not text:
                    continue
                scores[text] = scores.get(text, 0) + 1.0 / (k + rank + 1)
                if text not in texts:
                    texts[text] = {**item, "source": "bm25", "rrf_score": 0}

        # 更新分数并排序
        for text, score in scores.items():
            texts[text]["rrf_score"] = round(score, 6)

        sorted_items = sorted(texts.values(), key=lambda x: x["rrf_score"], reverse=True)
        return sorted_items

    def close(self) -> None:
        """关闭所有连接"""
        self.vector_store.disconnect()
        self.graph_store.close()
        logger.info("GraphRAG retriever closed")
