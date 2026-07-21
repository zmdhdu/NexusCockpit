# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Vector Store Base — 向量存储抽象基类

定义向量库的统一接口。本地 Milvus 与云端 Zilliz Cloud 都继承此类，
让上层 (检索器/记忆管理) 无需关心具体后端。

接口与现有 MilvusVectorStore 的公开方法保持一致，便于平滑迁移。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nexus.rag.embedding import EmbeddingService


class BaseVectorStore(ABC):
    """向量存储抽象接口。

    子类必须实现: 连接 / 记忆检索 / 记忆写入 / 记忆删除 / 食材检索 / 断开。
    """

    def __init__(self, embedding_service: EmbeddingService | None = None):
        self.embedding_service = embedding_service or EmbeddingService()

    @abstractmethod
    def connect(self) -> None:
        """连接向量库并初始化集合。"""
        raise NotImplementedError

    @abstractmethod
    async def search_memory(self, query_text: str, user_id: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索特定用户的语义记忆。"""
        raise NotImplementedError

    @abstractmethod
    async def insert_memory(self, text: str, user_id: str) -> int | None:
        """插入一条用户记忆，返回主键 ID。"""
        raise NotImplementedError

    @abstractmethod
    def delete_memory_by_ids(self, id_list: list[int], user_id: str) -> bool:
        """根据 ID 列表和 user_id 安全删除记忆。"""
        raise NotImplementedError

    @abstractmethod
    async def search_food(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索食材库。"""
        raise NotImplementedError

    @abstractmethod
    def drop_collection(self, name: str) -> bool:
        """删除集合（切换 embedding 维度时用）。"""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接。"""
        raise NotImplementedError

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError
