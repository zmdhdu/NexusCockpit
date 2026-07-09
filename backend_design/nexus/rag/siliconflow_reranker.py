"""
SiliconFlow Reranker — 硅基流动云端重排

调用硅基流动 Rerank API (POST {ARK_BASE_URL}/rerank), 复用 ARK_API_KEY。
使用免费模型 BAAI/bge-reranker-v2-m3。

请求体: {"model": ..., "query": ..., "documents": [...], "top_n": k}
响应:   {"results": [{"index": 0, "relevance_score": 0.99}, ...]}

注意: 硅基流动返回的是 index + score, 需映射回原 documents 列表,
      保持与 LocalReranker 相同输出结构 (每项加 rerank_score 字段)。
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.reranker_base import BaseReranker

logger = get_logger(__name__)


class SiliconFlowReranker(BaseReranker):
    """硅基流动云端重排服务。

    复用 LLM/Embedding 的 ARK_API_KEY + ARK_BASE_URL, 同一平台同一 Key。
    """

    def __init__(self):
        self.config = get_config().llm
        self.rerank_config = get_config().reranker
        self._client = httpx.AsyncClient(
            base_url=self.config.ark_base_url,
            headers={
                "Authorization": f"Bearer {self.config.ark_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        text_field: str = "text",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """对检索结果重排 (硅基流动 API)。

        硅基流动 API 为同步 HTTP, 这里用 httpx 同步调用 (rerank 在检索链路中是阻塞步骤)。
        """
        if not documents:
            return []

        # 提取每条文档的文本
        texts: List[str] = []
        valid_docs: List[Dict[str, Any]] = []
        for doc in documents:
            text = doc.get(text_field, "") or doc.get("content", "") or str(doc)
            if text:
                texts.append(text)
                valid_docs.append(doc)

        if not texts:
            return documents[:top_k]

        try:
            # 硅基流动 Rerank 接口 (同步调用)
            response = self._client.post(
                "/rerank",
                json={
                    "model": self.rerank_config.model,
                    "query": query,
                    "documents": texts,
                    "top_n": min(top_k, len(texts)),
                    "return_documents": False,
                },
            )
            response.raise_for_status()
            data = response.json()

            # 映射回原 documents, 加 rerank_score
            results: List[Dict[str, Any]] = []
            for item in data.get("results", []):
                idx = item.get("index")
                score = float(item.get("relevance_score", 0.0))
                if idx is not None and 0 <= idx < len(valid_docs):
                    doc_with_score = dict(valid_docs[idx])
                    doc_with_score["rerank_score"] = round(score, 6)
                    results.append(doc_with_score)

            logger.info(
                f"SiliconFlow rerank done: {len(documents)} → {len(results)} docs"
            )
            return results if results else documents[:top_k]

        except Exception as e:
            logger.error(f"SiliconFlow rerank failed: {e}, falling back to original order")
            return documents[:top_k]

    @property
    def is_available(self) -> bool:
        return bool(self.config.ark_api_key)
