# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Rerank 模型封装 — BAAI/bge-reranker-v2-m3

v2.0 新增模块:
  - 加载本地 bge-reranker-v2-m3 模型（约560MB）
  - 对检索结果 Top-N 重排，提升精度
  - 支持 GPU/CPU 推理，CPU 延迟约200ms/20条

模型路径: ./models/reranker/bge-reranker-v2-m3/
依赖: sentence-transformers>=2.7.0
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from nexus.core.logger import get_logger
from nexus.rag.reranker_base import BaseReranker

logger = get_logger(__name__)

# 模型默认路径
_DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "models", "reranker", "bge-reranker-v2-m3"
)


class LocalReranker(BaseReranker):
    """Rerank 重排服务。

    使用 BAAI/bge-reranker-v2-m3 模型对检索结果进行二次排序。
    模型首次加载约2秒，后续推理 CPU 约200ms/20条。

    Attributes:
        model_path: 模型文件路径
        _model: 加载的 CrossEncoder 模型实例
        _loaded: 是否已加载
    """

    def __init__(self, model_path: str = ""):
        self.model_path = model_path or _DEFAULT_MODEL_PATH
        self._model = None
        self._loaded = False
        self._load_error = ""

    def _ensure_loaded(self) -> bool:
        """延迟加载模型（首次调用时加载）。"""
        if self._loaded:
            return True
        if self._model is not None:
            return True

        if not os.path.exists(self.model_path):
            self._load_error = f"Model not found at {self.model_path}"
            logger.warning(self._load_error)
            return False

        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_path)
            self._loaded = True
            logger.info(f"Reranker model loaded from {self.model_path}")
            return True
        except ImportError:
            self._load_error = "sentence-transformers not installed"
            logger.warning(self._load_error)
            return False
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"Failed to load reranker model: {e}")
            return False

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        text_field: str = "text",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """对检索结果重排。

        Args:
            query: 查询文本
            documents: 检索结果列表（dict 列表）
            text_field: 文档中文本字段名
            top_k: 返回前 K 条

        Returns:
            重排后的 Top-K 结果列表，每项新增 rerank_score 字段
        """
        if not documents:
            return []

        # 模型不可用时直接返回原始结果的前 top_k 条
        if not self._ensure_loaded():
            return documents[:top_k]

        try:
            # 构建 query-document 对
            pairs = []
            valid_docs = []
            for doc in documents:
                text = doc.get(text_field, "") or doc.get("content", "") or str(doc)
                if text:
                    pairs.append((query, text))
                    valid_docs.append(doc)

            if not pairs:
                return documents[:top_k]

            # 批量推理
            scores = self._model.predict(pairs, show_progress_bar=False)

            # 按分数排序
            scored = list(zip(valid_docs, scores))
            scored.sort(key=lambda x: x[1], reverse=True)

            # 取 Top-K 并添加 rerank_score
            result = []
            for doc, score in scored[:top_k]:
                doc_with_score = dict(doc)
                doc_with_score["rerank_score"] = round(float(score), 6)
                result.append(doc_with_score)

            logger.info(
                f"Rerank done: {len(documents)} → {len(result)} docs, "
                f"top_score={result[0]['rerank_score']:.4f}" if result else "Rerank done: empty"
            )
            return result

        except Exception as e:
            logger.error(f"Rerank failed: {e}, falling back to original order")
            return documents[:top_k]

    @property
    def is_available(self) -> bool:
        """检查 reranker 是否可用（不触发加载）。"""
        return self._loaded or (
            os.path.exists(self.model_path) and self._load_error == ""
        )


# 向后兼容别名: 旧代码引用 RerankerService 仍可工作
RerankerService = LocalReranker
