# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
GraphRAG Retriever — 融合向量检索、图谱检索、BM25 全文检索

框架替换:
  - BM25Retriever (langchain-community) 替代手写 rank_bm25.BM25Okapi + jieba 分词
  - BM25Retriever 自带 preprocess_func 支持自定义分词

保留域特定逻辑:
  - 三路融合检索（向量+图谱+BM25）
  - RRF 融合排序
  - Rerank 后处理
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


def _chinese_tokenize(text: str) -> list[str]:
    """中文分词：jieba 优先，降级按字切分；英文按空格。"""
    import re
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    try:
        import jieba
        chinese_text = "".join(re.findall(r"[\u4e00-\u9fff]+", text))
        if chinese_text:
            tokens.extend(jieba.lcut(chinese_text))
    except ImportError:
        tokens.extend(re.findall(r"[\u4e00-\u9fff]", text))
    return [t for t in tokens if t.strip()]


class GraphRAGRetriever:
    """GraphRAG 三路融合检索器。

    三路召回 + RRF 融合 + Rerank 重排:
        - 向量路: Milvus 语义相似度召回
        - 图谱路: Neo4j 关系遍历召回
        - BM25路: langchain_community.BM25Retriever 全文匹配
        - 融合策略: RRF (Reciprocal Rank Fusion)
        - 后处理: bge-reranker-v2-m3 Rerank 重排
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
        self.reranker = reranker or (build_reranker() if enable_rerank else None)
        # BM25Retriever 实例（延迟初始化）
        self._bm25_retriever = None

    def connect(self) -> None:
        """连接所有存储。"""
        self.vector_store.connect()
        self.graph_store.connect()
        logger.info("GraphRAG retriever initialized (BM25 + Rerank)")

    def _init_bm25(self, documents: list[str]) -> None:
        """使用 langchain_community.BM25Retriever 初始化 BM25 索引。"""
        if not self.enable_bm25 or not documents:
            return
        try:
            from langchain_community.retrievers import BM25Retriever
            from langchain_core.documents import Document
            # 使用自定义中文分词函数
            self._bm25_retriever = BM25Retriever.from_documents(
                [Document(page_content=doc) for doc in documents],
                k=10,
                preprocess_func=_chinese_tokenize,
            )
            logger.info(f"BM25Retriever initialized with {len(documents)} docs")
        except ImportError:
            logger.warning("langchain-community not installed, BM25 retrieval disabled")
            self.enable_bm25 = False
        except Exception as e:
            logger.error(f"BM25 init failed: {e}")
            self.enable_bm25 = False

    def _bm25_search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """BM25 全文检索（使用 BM25Retriever）。"""
        if not self._bm25_retriever:
            return []
        try:
            docs = self._bm25_retriever.invoke(query)
            results = []
            for i, doc in enumerate(docs[:top_k]):
                results.append({
                    "text": doc.page_content,
                    "score": 1.0 / (i + 1),  # BM25Retriever 不返回 score，用 rank 近似
                    "source": "bm25",
                })
            return results
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    async def retrieve_memories(
        self, query: str, user_id: str, top_k: int = 5, graph_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """三路融合检索用户记忆。"""
        vec_results = await self.vector_store.search_memory(query, user_id, top_k=top_k * 4)
        graph_results = self.graph_store.search_user_graph(user_id, depth=graph_depth)
        bm25_results: list[dict[str, Any]] = []
        if self.enable_bm25 and self._bm25_retriever:
            bm25_results = self._bm25_search(query, top_k=top_k * 2)
        fused = self._rrf_fuse(vec_results, graph_results, bm25_results)
        if self.reranker and len(fused) > top_k:
            fused = self.reranker.rerank(query, fused, top_k=top_k)
        return fused[:top_k]

    async def retrieve_food(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索食材库。"""
        vec_results = await self.vector_store.search_food(query, top_k=top_k)
        graph_match = self.graph_store.search_food(query)
        if graph_match and not any(r.get("item_name") == graph_match for r in vec_results):
            vec_results.insert(0, {"item_name": graph_match, "score": 1.0, "source": "graph"})
        return vec_results[:top_k]

    def _rrf_fuse(
        self, vec_results: list[dict[str, Any]], graph_results: list[str],
        bm25_results: list[dict[str, Any]] = None, k: int = 60,
    ) -> list[dict[str, Any]]:
        """RRF (Reciprocal Rank Fusion) 三路融合排序。"""
        scores: dict[str, float] = {}
        texts: dict[str, dict[str, Any]] = {}

        for rank, item in enumerate(vec_results):
            text = item.get("text", "")
            if not text:
                continue
            scores[text] = scores.get(text, 0) + 1.0 / (k + rank + 1)
            texts[text] = {**item, "source": "vector", "rrf_score": 0}

        for rank, text in enumerate(graph_results):
            scores[text] = scores.get(text, 0) + 1.0 / (k + rank + 1)
            if text not in texts:
                texts[text] = {"text": text, "source": "graph", "rrf_score": 0}

        if bm25_results:
            for rank, item in enumerate(bm25_results):
                text = item.get("text", "")
                if not text:
                    continue
                scores[text] = scores.get(text, 0) + 1.0 / (k + rank + 1)
                if text not in texts:
                    texts[text] = {**item, "source": "bm25", "rrf_score": 0}

        for text, score in scores.items():
            texts[text]["rrf_score"] = round(score, 6)

        return sorted(texts.values(), key=lambda x: x["rrf_score"], reverse=True)

    def close(self) -> None:
        """关闭所有连接。"""
        self.vector_store.disconnect()
        self.graph_store.close()
        logger.info("GraphRAG retriever closed")
