"""
Milvus Vector Store — 向量存储与检索

管理两个 Milvus Collection:
  1. Food_List  — 食材知识库向量
  2. User_Memory — 用户长期记忆向量

支持语义搜索: 将查询文本转向量后在 Milvus 中做 ANN 近似搜索。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from nexus.config import get_config
from nexus.core.exceptions import VectorStoreError
from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_base import BaseVectorStore

logger = get_logger(__name__)


class MilvusVectorStore(BaseVectorStore):
    """Milvus 向量数据库管理器。

    Args:
        embedding_service: 文本向量化服务
    """

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.config = get_config().milvus
        self.embedding_service = embedding_service or EmbeddingService()
        self._connected = False
        self.food_collection: Optional[Collection] = None
        self.memory_collection: Optional[Collection] = None

    def connect(self) -> None:
        """连接 Milvus 并初始化集合"""
        try:
            connections.connect(
                alias=self.config.alias,
                uri=self.config.uri,
                token=self.config.token or "",
            )
            self._connected = True
            logger.info(
                "Milvus connected",
                uri=self.config.uri,
                alias=self.config.alias,
            )
            self._init_food_collection()
            self._init_memory_collection()
        except Exception as e:
            logger.error(f"Milvus connection failed: {e}")
            raise VectorStoreError(f"Failed to connect to Milvus: {e}")

    def _init_food_collection(self) -> None:
        """初始化食材集合"""
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
                index_params={
                    "metric_type": self.config.metric_type,
                    "index_type": self.config.index_type,
                    "params": self.config.index_params,
                },
            )
            self.food_collection.load()
            logger.info(f"Food collection created: {name}")

    def _init_memory_collection(self) -> None:
        """初始化用户记忆集合"""
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
                index_params={
                    "metric_type": self.config.metric_type,
                    "index_type": self.config.index_type,
                    "params": {"M": 8, "efConstruction": 64},
                },
            )
            self.memory_collection.create_index(
                field_name="user_id",
                index_params={"index_type": "Trie"},
            )
            self.memory_collection.load()
            logger.info(f"Memory collection created: {name}")

    async def search_memory(self, query_text: str, user_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """检索特定用户的语义记忆"""
        if not self.memory_collection:
            return []

        vec = await self.embedding_service.embed(query_text)
        if not vec:
            return []

        try:
            results = self.memory_collection.search(
                data=[vec],
                anns_field="vector",
                param={
                    "metric_type": self.config.metric_type,
                    "params": self.config.search_params,
                },
                limit=top_k,
                expr=f'user_id == "{user_id}"',
                output_fields=["text", "id", "user_id", "timestamp"],
            )

            memories = []
            if results and results[0]:
                for hit in results[0]:
                    memories.append({
                        "id": hit.id,
                        "text": hit.entity.get("text"),
                        "score": float(hit.distance),
                        "timestamp": hit.entity.get("timestamp"),
                    })
            return memories
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []

    async def insert_memory(self, text: str, user_id: str) -> Optional[int]:
        """插入一条用户记忆，返回主键 ID"""
        if not self.memory_collection:
            return None

        vec = await self.embedding_service.embed(text)
        if not vec:
            return None

        try:
            data = [
                [user_id],
                [vec],
                [text[:1000]],
                [int(time.time())],
            ]
            result = self.memory_collection.insert(data)
            inserted_id = int(result.primary_keys[0])
            logger.info(f"Memory inserted: id={inserted_id}, user={user_id}")
            return inserted_id
        except Exception as e:
            logger.error(f"Memory insert failed: {e}")
            return None

    def delete_memory_by_ids(self, id_list: List[int], user_id: str) -> bool:
        """根据 ID 列表和 user_id 安全删除记忆"""
        if not self.memory_collection or not id_list:
            return False

        try:
            expr = f"id in {id_list} and user_id == '{user_id}'"
            self.memory_collection.delete(expr)
            self.memory_collection.flush()
            logger.info(f"Memories deleted: ids={id_list}, user={user_id}")
            return True
        except Exception as e:
            logger.error(f"Memory delete failed: {e}")
            return False

    async def search_food(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """检索食材库"""
        if not self.food_collection:
            return []

        vec = await self.embedding_service.embed(query_text)
        if not vec:
            return []

        try:
            results = self.food_collection.search(
                data=[vec],
                anns_field="vector",
                param={
                    "metric_type": self.config.metric_type,
                    "params": self.config.search_params,
                },
                limit=top_k,
                output_fields=["item_name", "category_name", "cate_1_name", "cate_2_name", "cate_3_name"],
            )

            foods = []
            if results and results[0]:
                for hit in results[0]:
                    foods.append({
                        "id": hit.id,
                        "score": float(hit.distance),
                        "item_name": hit.entity.get("item_name"),
                        "category_name": hit.entity.get("category_name"),
                        "cate_1_name": hit.entity.get("cate_1_name"),
                        "cate_2_name": hit.entity.get("cate_2_name"),
                        "cate_3_name": hit.entity.get("cate_3_name"),
                    })
            return foods
        except Exception as e:
            logger.error(f"Food search failed: {e}")
            return []

    def drop_collection(self, name: str) -> bool:
        """删除集合"""
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
        """断开连接"""
        try:
            connections.disconnect(alias=self.config.alias)
            self._connected = False
            logger.info("Milvus disconnected")
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        return self._connected
