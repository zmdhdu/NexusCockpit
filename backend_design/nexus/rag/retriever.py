"""
GraphRAG Retriever — 融合向量检索与图谱检索

GraphRAG 是 NexusCockpit 的核心检索策略，通过双路召回 + 排序融合提升检索质量:
  - 向量路: Milvus 语义相似度召回 (基于文本含义匹配)
  - 图谱路: Neo4j 关系遍历召回 (基于实体关系匹配)
  - 融合策略: RRF (Reciprocal Rank Fusion) 倒数排名融合

优势: 向量路擅长语义模糊匹配，图谱路擅长精确关系推理，两者互补。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService
from nexus.rag.graph_store import Neo4jGraphStore
from nexus.rag.vector_store import MilvusVectorStore

logger = get_logger(__name__)


class GraphRAGRetriever:
    """GraphRAG 融合检索器。

    双路召回 + RRF 融合排序:
        - 向量路: Milvus 语义相似度召回
        - 图谱路: Neo4j 关系遍历召回
        - 融合策略: RRF (Reciprocal Rank Fusion) 排序

    Args:
        vector_store: Milvus 向量存储
        graph_store: Neo4j 图谱存储
        embedding_service: 文本向量化服务
    """

    def __init__(
        self,
        vector_store: Optional[MilvusVectorStore] = None,
        graph_store: Optional[Neo4jGraphStore] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or MilvusVectorStore(self.embedding_service)
        self.graph_store = graph_store or Neo4jGraphStore()

    def connect(self) -> None:
        """连接所有存储"""
        self.vector_store.connect()
        self.graph_store.connect()
        logger.info("GraphRAG retriever initialized")

    async def retrieve_memories(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        graph_depth: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        融合检索用户记忆
        返回去重排序后的记忆列表
        """
        # 向量路召回
        vec_results = await self.vector_store.search_memory(query, user_id, top_k=top_k * 2)

        # 图谱路召回
        graph_results = self.graph_store.search_user_graph(user_id, depth=graph_depth)

        # RRF 融合排序
        fused = self._rrf_fuse(vec_results, graph_results)

        return fused[:top_k]

    async def retrieve_food(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """检索食材库"""
        # 向量路
        vec_results = await self.vector_store.search_food(query, top_k=top_k)

        # 图谱路
        graph_match = self.graph_store.search_food(query)

        # 合并
        if graph_match and not any(
            r.get("item_name") == graph_match for r in vec_results
        ):
            vec_results.insert(0, {"item_name": graph_match, "score": 1.0, "source": "graph"})

        return vec_results[:top_k]

    def _rrf_fuse(
        self,
        vec_results: List[Dict[str, Any]],
        graph_results: List[str],
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        """RRF (Reciprocal Rank Fusion) 融合排序。

        公式: RRF(d) = Σ 1/(k + rank_i(d))
        其中 k 是平滑常数 (默认 60)，rank_i 是文档在第 i 路结果中的排名。

        Args:
            vec_results: 向量路召回结果
            graph_results: 图谱路召回结果 (文本列表)
            k: 平滑常数

        Returns:
            融合排序后的结果列表
        """
        scores: Dict[str, float] = {}
        texts: Dict[str, Dict[str, Any]] = {}

        # 向量路打分
        for rank, item in enumerate(vec_results):
            text = item.get("text", "")
            if not text:
                continue
            scores[text] = scores.get(text, 0) + 1.0 / (k + rank + 1)
            texts[text] = {**item, "source": "vector", "rrf_score": 0}

        # 图谱路打分 (graph_results 是字符串列表)
        for rank, text in enumerate(graph_results):
            scores[text] = scores.get(text, 0) + 1.0 / (k + rank + 1)
            if text not in texts:
                texts[text] = {"text": text, "source": "graph", "rrf_score": 0}

        # 更新分数并排序
        for text, score in scores.items():
            texts[text]["rrf_score"] = round(score, 6)
            texts[text]["source"] = (
                "fusion" if texts[text]["source"] in ("vector", "graph") and scores[text] > 0.02
                else texts[text]["source"]
            )

        sorted_items = sorted(texts.values(), key=lambda x: x["rrf_score"], reverse=True)
        return sorted_items

    def close(self) -> None:
        """关闭所有连接"""
        self.vector_store.disconnect()
        self.graph_store.close()
        logger.info("GraphRAG retriever closed")
