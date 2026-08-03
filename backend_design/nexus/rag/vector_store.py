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

已迁移到 pymilvus 3.x MilvusClient API（替代 ORM 风格 connections/Collection/utility）。
"""

from __future__ import annotations

import time
from typing import Any

from pymilvus import DataType, MilvusClient

from nexus.config import get_config
from nexus.core.exceptions import VectorStoreError
from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_base import BaseVectorStore

logger = get_logger(__name__)


class MilvusVectorStore(BaseVectorStore):
    """Milvus 向量数据库管理器（MilvusClient API）。"""

    def __init__(self, embedding_service: EmbeddingService | None = None):
        self.config = get_config().milvus
        self.embedding_service = embedding_service or EmbeddingService()
        self._client: MilvusClient | None = None
        self._connected = False

    def connect(self) -> None:
        """连接 Milvus 并初始化集合（幂等，重复调用不会重连）。"""
        if self._connected and self._client:
            return
        try:
            self._client = MilvusClient(uri=self.config.uri)
            self._connected = True
            logger.info("Milvus connected", uri=self.config.uri)
            self._init_food_collection()
            self._init_memory_collection()
        except Exception as e:
            logger.error(f"Milvus connection failed: {e}")
            raise VectorStoreError(f"Failed to connect to Milvus: {e}")

    def _check_vector_dim(self, collection_name: str, expected_dim: int) -> bool:
        """检查 collection 的向量维度是否与配置一致。

        Args:
            collection_name: 集合名称
            expected_dim: 配置中的期望维度

        Returns:
            True 如果维度匹配，False 如果不匹配
        """
        try:
            desc = self._client.describe_collection(collection_name=collection_name)
            for field in desc.get("fields", []):
                params = field.get("params", {})
                if "dim" in params:
                    actual_dim = int(params["dim"])
                    if actual_dim != expected_dim:
                        logger.warning(
                            f"Collection '{collection_name}' vector dim mismatch: "
                            f"expected {expected_dim}, got {actual_dim}"
                        )
                        return False
                    return True
        except Exception as e:
            logger.debug(f"Vector dim check failed (assuming ok): {e}")
        return True

    def _check_field_exists(self, collection_name: str, field_name: str) -> bool:
        """检查 collection 中是否存在指定字段（用于 schema 迁移检测）。

        Args:
            collection_name: 集合名称
            field_name: 待检查的字段名

        Returns:
            True 如果字段存在，False 如果不存在
        """
        try:
            desc = self._client.describe_collection(collection_name=collection_name)
            for field in desc.get("fields", []):
                if field.get("name") == field_name:
                    return True
            return False
        except Exception as e:
            logger.debug(f"Field check failed for '{field_name}': {e}")
            return True  # 检查失败时不触发重建，避免误删数据

    def _init_food_collection(self) -> None:
        """初始化食材集合。"""
        name = self.config.collection_food
        expected_dim = get_config().llm.embedding_dim

        if self._client.has_collection(collection_name=name):
            if not self._check_vector_dim(name, expected_dim):
                logger.warning(
                    f"Dropping collection '{name}' due to dim mismatch, recreating with dim={expected_dim}"
                )
                self._client.drop_collection(collection_name=name)
            else:
                self._client.load_collection(collection_name=name)
                logger.info(f"Food collection loaded: {name}")
                return

        # 创建新集合
        schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=expected_dim)
        schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="category_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="cate_1_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="cate_2_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="cate_3_name", datatype=DataType.VARCHAR, max_length=255)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type=self.config.index_type,
            metric_type=self.config.metric_type,
            params=self.config.index_params,
        )

        self._client.create_collection(
            collection_name=name,
            schema=schema,
            index_params=index_params,
        )
        self._client.load_collection(collection_name=name)
        logger.info(f"Food collection created: {name}")

    def _init_memory_collection(self) -> None:
        """初始化用户记忆集合。"""
        name = self.config.collection_memory
        expected_dim = get_config().llm.embedding_dim

        if self._client.has_collection(collection_name=name):
            need_recreate = False
            if not self._check_vector_dim(name, expected_dim):
                logger.warning(
                    f"Dropping collection '{name}' due to dim mismatch, recreating with dim={expected_dim}"
                )
                need_recreate = True
            elif not self._check_field_exists(name, "session_id"):
                logger.warning(
                    f"Dropping collection '{name}' due to missing 'session_id' field, "
                    f"recreating with session-scoped schema"
                )
                need_recreate = True

            if need_recreate:
                self._client.drop_collection(collection_name=name)
            else:
                self._client.load_collection(collection_name=name)
                logger.info(f"Memory collection loaded: {name}")
                return

        # 创建新集合（含 session_id 字段，支持会话级记忆隔离与清理）
        schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="user_id", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="session_id", datatype=DataType.VARCHAR, max_length=80)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=expected_dim)
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=1000)
        schema.add_field(field_name="timestamp", datatype=DataType.INT64)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type=self.config.index_type,
            metric_type=self.config.metric_type,
            params={"M": 8, "efConstruction": 64},
        )
        index_params.add_index(field_name="user_id", index_type="Trie")
        index_params.add_index(field_name="session_id", index_type="Trie")

        self._client.create_collection(
            collection_name=name,
            schema=schema,
            index_params=index_params,
        )
        self._client.load_collection(collection_name=name)
        logger.info(f"Memory collection created: {name}")

    async def search_memory(self, query_text: str, user_id: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索特定用户的语义记忆。"""
        if not self._client:
            return []
        vec = await self.embedding_service.embed(query_text)
        if not vec:
            return []
        try:
            results = self._client.search(
                collection_name=self.config.collection_memory,
                data=[vec],
                anns_field="vector",
                search_params={"metric_type": self.config.metric_type, "params": self.config.search_params},
                limit=top_k,
                filter=f'user_id == "{user_id}"',
                output_fields=["text", "id", "user_id", "timestamp"],
            )
            memories = []
            if results and results[0]:
                for hit in results[0]:
                    entity = hit.get("entity", {})
                    memories.append({
                        "id": hit.get("id"),
                        "text": entity.get("text"),
                        "score": float(hit.get("distance", 0)),
                        "timestamp": entity.get("timestamp"),
                    })
            return memories
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []

    async def insert_memory(self, text: str, user_id: str, session_id: str = "") -> int | None:
        """插入一条用户记忆，返回主键 ID。

        Args:
            text: 记忆文本
            user_id: 用户 ID
            session_id: 会话 ID（空字符串表示用户级记忆，如提取的事实/偏好）
        """
        if not self._client:
            return None
        vec = await self.embedding_service.embed(text)
        if not vec:
            return None
        try:
            result = self._client.insert(
                collection_name=self.config.collection_memory,
                data=[{
                    "user_id": user_id,
                    "session_id": session_id,
                    "vector": vec,
                    "text": text[:1000],
                    "timestamp": int(time.time()),
                }],
            )
            inserted_id = int(result["ids"][0])
            logger.info(f"Memory inserted: id={inserted_id}, user={user_id}, session={session_id or 'N/A'}")
            return inserted_id
        except Exception as e:
            logger.error(f"Memory insert failed: {e}")
            return None

    def delete_memory_by_ids(self, id_list: list[int], user_id: str) -> bool:
        """根据 ID 列表和 user_id 安全删除记忆。"""
        if not self._client or not id_list:
            return False
        try:
            self._client.delete(
                collection_name=self.config.collection_memory,
                filter=f"id in {id_list} and user_id == '{user_id}'",
            )
            logger.info(f"Memories deleted: ids={id_list}, user={user_id}")
            return True
        except Exception as e:
            logger.error(f"Memory delete failed: {e}")
            return False

    def delete_memory_by_session(self, session_id: str, user_id: str = "") -> int:
        """删除指定会话的所有记忆向量（会话级清理）。

        仅删除 session_id 匹配的记忆，不影响用户级记忆（session_id 为空的事实/偏好）。
        用于删除会话时清理该会话产生的对话向量。

        Args:
            session_id: 会话 ID
            user_id: 用户 ID（双重校验，确保不跨用户删除）

        Returns:
            删除的记录数（估算），失败返回 0
        """
        if not self._client or not session_id:
            return 0
        try:
            # 先查询该会话的记忆数量（用于日志）
            filter_expr = f"session_id == '{session_id}'"
            if user_id:
                filter_expr += f" and user_id == '{user_id}'"

            count_result = self._client.query(
                collection_name=self.config.collection_memory,
                filter=filter_expr,
                output_fields=["id"],
                limit=16384,
            )
            deleted_count = len(count_result) if count_result else 0

            if deleted_count == 0:
                logger.debug(f"No session-scoped memories found for session='{session_id}'")
                return 0

            # 执行删除
            self._client.delete(
                collection_name=self.config.collection_memory,
                filter=filter_expr,
            )
            logger.info(
                f"Session memories deleted: session='{session_id}', "
                f"user='{user_id}', count={deleted_count}"
            )
            return deleted_count
        except Exception as e:
            logger.error(f"Session memory delete failed: {e}")
            return 0

    async def search_food(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索食材库。"""
        if not self._client:
            return []
        vec = await self.embedding_service.embed(query_text)
        if not vec:
            return []
        try:
            results = self._client.search(
                collection_name=self.config.collection_food,
                data=[vec],
                anns_field="vector",
                search_params={"metric_type": self.config.metric_type, "params": self.config.search_params},
                limit=top_k,
                output_fields=["item_name", "category_name", "cate_1_name", "cate_2_name", "cate_3_name"],
            )
            foods = []
            if results and results[0]:
                for hit in results[0]:
                    entity = hit.get("entity", {})
                    foods.append({
                        "id": hit.get("id"),
                        "score": float(hit.get("distance", 0)),
                        "item_name": entity.get("item_name"),
                        "category_name": entity.get("category_name"),
                        "cate_1_name": entity.get("cate_1_name"),
                        "cate_2_name": entity.get("cate_2_name"),
                        "cate_3_name": entity.get("cate_3_name"),
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
        emb = getattr(self.embedding_service, '_embeddings', None)
        return Milvus(
            embedding_function=emb,
            collection_name=collection_name or self.config.collection_memory,
            connection_args={"uri": self.config.uri},
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
            if self._client.has_collection(collection_name=name):
                self._client.drop_collection(collection_name=name)
                logger.info(f"Collection dropped: {name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Collection drop failed: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接。"""
        try:
            if self._client:
                self._client.close()
            self._connected = False
            logger.info("Milvus disconnected")
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        return self._connected
