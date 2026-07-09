"""
Reranker Base — 重排抽象基类

定义重排服务的统一接口。本地 BGE CrossEncoder 与云端硅基流动 Rerank 都继承此类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseReranker(ABC):
    """重排服务抽象接口。

    子类必须实现 rerank(): 对检索结果按与 query 的相关度重排序, 返回 Top-K。
    输出约定: 每项新增 rerank_score 字段, 与现有 LocalReranker 保持一致。
    """

    @abstractmethod
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
            documents: 检索结果列表 (dict 列表)
            text_field: 文档中文本字段名
            top_k: 返回前 K 条

        Returns:
            重排后的 Top-K 结果列表, 每项新增 rerank_score 字段
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """检查 reranker 是否可用。"""
        raise NotImplementedError
