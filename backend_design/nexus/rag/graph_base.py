# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Graph Store Base — 知识图谱存储抽象基类

定义图谱库的统一接口。本地 Neo4j 与云端 AuraDB 都继承此类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseGraphStore(ABC):
    """知识图谱抽象接口。

    子类必须实现: 连接 / 关系增删 / 用户图谱查询 / 食材查询 / 画像 / 清库 / 关闭。
    """

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_relation(
        self,
        user_id: str,
        relation: str,
        target: str,
        target_type: str,
        milvus_id: int,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_relation_by_mid(self, milvus_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def search_user_graph(self, user_id: str, depth: int = 1) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def search_food(self, food_name: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def clear_database(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
