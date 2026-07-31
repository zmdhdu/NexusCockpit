# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Milvus Vector Store — 向量存储与检索

管理两个 Milvus Collection:
  1. Food_List  — 食材知识库向量
  2. User_Memory — 用户长期记忆向量

框架组件:
  - EmbeddingService 内部已使用 langchain_openai.OpenAIEmbeddings
  - as_langchain_store() 返回 langchain_milvus.Milvus 实例（用于 RAG 检索）
  - 领域特定搜索（food/memory with user_id filter）保留 pymilvus 直接操作
"""

from __future__ import annotations

import time
from typing import Any

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from nexus.config import get_config
from nexus.core.exceptions import VectorStoreError
from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_base import BaseVectorStore

logger = get_logger(__name__)


class MilvusVectorStore(BaseVectorStore):
    """Milvus 向量数据库管理器。"""

    def __init__(self, embedding_service: EmbeddingService | None = None):
        self.config = get_config().milvus
        self.embedding_service = embedding_service or EmbeddingService()
        self._connected = False
        self.food_collection: Collection | None = None
        self.memory_collection: Collection | None = None

    def connect(self) -> None:
        """连接 Milvus 并初始化集合。"""
        try:
            connections.connect(alias=self.config.alias, uri=self.config.uri, token="")
            self._connected = True
            logger.info("Milvus connected", uri=self.config.uri, alias=self.config.alias)
            self._init_food_collection()
            self._init_memory_collection()
        except Exception as e:
            logger.error(f"Milvus connection failed: {e}")
            raise VectorStoreError(f"Failed to connect to Milvus: {e}")

    def _init_food_collection(self) -> None:
        """初始化食材集合。"""
        name = self.config.collection_food
        if utility.has_collection(name, using=self.config.alias):
            self.food_collection = Collection(name=name, using=self.config.alias)
            self.food_collection.load()
            logger.info(f"Food collection loaded: {name}")
        else:
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=get_config().llm.embedding_dim),
                FieldSchema(name="item_name", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="category_name", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="cate_1_name", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="cate_2_name", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="cate_3_name", dtype=DataType.VARCHAR, max_length=255),
            ]
            schema = CollectionSchema(fields=fields, description="Food item vectors", enable_dynamic_field=False)
            self.food_collection = Collection(name=name, schema=schema, using=self.config.alias)
            self.food_collection.create_index(
                field_name="vector",
                index_params={"metric_type": self.config.metric_type, "index_type": self.config.index_type, "params": self.config.index_params},
            )
            self.food_collection.load()
            logger.info(f"Food collection created: {name}")

    def _init_memory_collection(self) -> None:
        """初始化用户记忆集合。"""
        name = self.config.collection_memory
        if utility.has_collection(name, using=self.config.alias):
            self.memory_collection = Collection(name=name, using=self.config.alias)
            self.memory_collection.load()
            logger.info(f"Memory collection loaded: {name}")
        else:
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=get_config().llm.embedding_dim),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=1000),
                FieldSchema(name="timestamp", dtype=DataType.INT64),
            ]
            schema = CollectionSchema(fields=fields, description="User long-term memory")
            self.memory_collection = Collection(name=name, schema=schema, using=self.config.alias)
            self.memory_collection.create_index(
                field_name="vector",
                index_params={"metric_type": self.config.metric_type, "index_type": self.config.index_type, "params": {"M": 8, "efConstruction": 64}},
            )
            self.memory_collection.create_index(field_name="user_id", index_params={"index_type": "Trie"})
            self.memory_collection.load()
            logger.info(f"Memory collection created: {name}")

    async def search_memory(self, query_text: str, user_id: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索特定用户的语义记忆。"""
        if not self.memory_collection:
            return []
        vec = await self.embedding_service.embed(query_text)
        if not vec:
            return []
        try:
            results = self.memory_collection.search(
                data=[vec], anns_field="vector",
                param={"metric_type": self.config.metric_type, "params": self.config.search_params},
                limit=top_k, expr=f'user_id == "{user_id}"',
                output_fields=["text", "id", "user_id", "timestamp"],
            )
            memories = []
            if results and results[0]:
                for hit in results[0]:
                    memories.append({"id": hit.id, "text": hit.entity.get("text"), "score": float(hit.distance), "timestamp": hit.entity.get("timestamp")})
            return memories
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []

    async def insert_memory(self, text: str, user_id: str) -> int | None:
        """插入一条用户记忆，返回主键 ID。"""
        if not self.memory_collection:
            return None
        vec = await self.embedding_service.embed(text)
        if not vec:
            return None
        try:
            result = self.memory_collection.insert([[user_id], [vec], [text[:1000]], [int(time.time())]])
            inserted_id = int(result.primary_keys[0])
            logger.info(f"Memory inserted: id={inserted_id}, user={user_id}")
            return inserted_id
        except Exception as e:
            logger.error(f"Memory insert failed: {e}")
            return None

    def delete_memory_by_ids(self, id_list: list[int], user_id: str) -> bool:
        """根据 ID 列表和 user_id 安全删除记忆。"""
        if not self.memory_collection or not id_list:
            return False
        try:
            self.memory_collection.delete(expr=f"id in {id_list} and user_id == '{user_id}'")
            self.memory_collection.flush()
            logger.info(f"Memories deleted: ids={id_list}, user={user_id}")
            return True
        except Exception as e:
            logger.error(f"Memory delete failed: {e}")
            return False

    async def search_food(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索食材库。"""
        if not self.food_collection:
            return []
        vec = await self.embedding_service.embed(query_text)
        if not vec:
            return []
        try:
            results = self.food_collection.search(
                data=[vec], anns_field="vector",
                param={"metric_type": self.config.metric_type, "params": self.config.search_params},
                limit=top_k,
                output_fields=["item_name", "category_name", "cate_1_name", "cate_2_name", "cate_3_name"],
            )
            foods = []
            if results and results[0]:
                for hit in results[0]:
                    foods.append({
                        "id": hit.id, "score": float(hit.distance),
                        "item_name": hit.entity.get("item_name"), "category_name": hit.entity.get("category_name"),
                        "cate_1_name": hit.entity.get("cate_1_name"), "cate_2_name": hit.entity.get("cate_2_name"),
                        "cate_3_name": hit.entity.get("cate_3_name"),
                    })
            return foods
        except Exception as e:
            logger.error(f"Food search failed: {e}")
            return []

    def as_langchain_store(self, collection_name: str = ""):
        """获取 langchain_milvus.Milvus 实例（用于 LangChain RAG 检索）。

        返回的 Milvus 实例可用于:
          - store.as_retriever() → LangChain Retriever
          - store.similarity_search() → 通用向量搜索
          - store.add_texts() → 通用文本入库

        注意: 此实例使用 LangChain 标准 schema (page_content + metadata)，
        不适用于已有的 Food_List/User_Memory 集合（它们有自定义 schema）。
        适用于新建的通用知识库集合。

        Args:
            collection_name: 集合名（默认使用 memory collection 名）

        Returns:
            langchain_milvus.Milvus 实例
        """
        from langchain_milvus import Milvus
        return Milvus(
            embedding_function=self.embedding_service._embeddings if hasattr(self.embedding_service, '_embeddings') else None,
            collection_name=collection_name or self.config.collection_memory,
            connection_args={"uri": self.config.uri, "alias": self.config.alias},
            index_params={
                "index_type": self.config.index_type,
                "metric_type": self.config.metric_type,
                "params": self.config.index_params,
            },
            auto_id=True,
        )

    def drop_collection(self, name: str) -> bool:
        """删除集合。"""
        try:
            if utility.has_collection(name, using=self.config.alias):
                Collection(name=name, using=self.config.alias).drop()
                logger.info(f"Collection dropped: {name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Collection drop failed: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接。"""
        try:
            connections.disconnect(alias=self.config.alias)
            self._connected = False
            logger.info("Milvus disconnected")
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        return self._connected
