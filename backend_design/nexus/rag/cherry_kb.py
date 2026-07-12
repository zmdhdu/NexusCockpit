"""
Cherry Knowledge Base — 文档型知识库

v2.0 新增模块:
  - 基于 Milvus 文档向量集合存储长文档（车手册、故障码、FAQ、保养规范）
  - 完整链路: 文档分块 → Embedding → Milvus 存储 → KBRetriever 检索
  - 与 GraphRAG（记忆/习惯）分层互补

集合名: nexus_kb_docs
字段:
  - id: 文档块 ID
  - text: 文档块文本
  - source: 文档来源（文件名）
  - category: 文档类别（manual/dtc/faq/maintenance）
  - vector: Embedding 向量
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService

# langchain-text-splitters 1.0+ 提供的递归字符文本分割器
# 支持多级分隔符（段落 → 句子 → 字符），比简单滑动窗口更智能
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    _HAS_LANGCHAIN_SPLITTER = True
except ImportError:
    _HAS_LANGCHAIN_SPLITTER = False

logger = get_logger(__name__)

_COLLECTION_NAME = "nexus_kb_docs"
_CHUNK_SIZE = 500  # 每块约500字
_CHUNK_OVERLAP = 50  # 块间重叠50字
# 中文优先分隔符：段落 > 句号 > 感叹号 > 问号 > 分号 > 逗号 > 空格 > 字符
_CHUNK_SEPARATORS = ["\n\n", "\n", "。", "！", "？", ";", "；", ",", "，", " ", ""]


class CherryKnowledgeBase:
    """Cherry 文档知识库。

    管理文档的入库、分块、向量化、检索全流程。
    基于 Milvus 存储，不引入新向量库组件。

    Args:
        embedding_service: 文本向量化服务
        milvus_client: Milvus 连接客户端（pymilvus）
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        milvus_client=None,
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self._client = milvus_client
        self._connected = False
        # Milvus 连接别名，从配置读取 (与 MilvusVectorStore 使用相同的别名)
        self._milvus_alias = get_config().milvus.alias

        # 初始化 langchain_text_splitters 1.0+ 的 RecursiveCharacterTextSplitter
        # 支持中英文多级分隔符递归分割，比简单滑动窗口更自然
        if _HAS_LANGCHAIN_SPLITTER:
            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=_CHUNK_SIZE,
                chunk_overlap=_CHUNK_OVERLAP,
                separators=_CHUNK_SEPARATORS,
                keep_separator=True,
            )
        else:
            self._splitter = None

    def connect(self, milvus_client=None) -> None:
        """连接 Milvus 并确保集合存在。

        Args:
            milvus_client: 可选的 Milvus 客户端标志。如果传入 truthy 值，
                           表示 Milvus 已由外部连接，直接使用。
        """
        if milvus_client:
            self._client = milvus_client
        if self._client:
            self._connected = True
            self._ensure_collection()
            logger.info("Cherry KnowledgeBase connected")
        else:
            logger.warning("Cherry KnowledgeBase: no Milvus client")

    def _ensure_collection(self) -> None:
        """确保 kb_docs 集合存在，不存在则创建。"""
        if not self._client:
            return
        try:
            from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, utility

            if utility.has_collection(_COLLECTION_NAME, using=self._milvus_alias):
                logger.info(f"KB collection '{_COLLECTION_NAME}' already exists")
                return

            # 定义集合 schema
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=4096),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=get_config().llm.embedding_dim),
            ]
            schema = CollectionSchema(fields, description="NexusCockpit Knowledge Base Docs")
            collection = Collection(_COLLECTION_NAME, schema, using=self._milvus_alias)

            # 创建 IVF_FLAT 索引
            collection.create_index(
                field_name="vector",
                index_params={
                    "index_type": "IVF_FLAT",
                    "metric_type": "COSINE",
                    "params": {"nlist": 128},
                },
            )
            logger.info(f"KB collection '{_COLLECTION_NAME}' created with index")
        except Exception as e:
            logger.error(f"Failed to ensure KB collection: {e}")

    def add_document(
        self,
        text: str,
        source: str = "unknown",
        category: str = "general",
    ) -> int:
        """添加文档到知识库（分块 + 向量化 + 入库）。

        Args:
            text: 文档全文
            source: 文档来源（文件名）
            category: 文档类别（manual/dtc/faq/maintenance）

        Returns:
            入库的文档块数量
        """
        if not self._connected or not self._client:
            logger.warning("KB not connected, document not added")
            return 0

        # 分块（使用 langchain_text_splitters RecursiveCharacterTextSplitter）
        chunks = self._chunk_text(text)
        if not chunks:
            return 0

        try:
            from pymilvus import Collection

            collection = Collection(_COLLECTION_NAME, using=self._milvus_alias)

            # 批量向量化
            embeddings = self.embedding_service.embed_batch(chunks)

            # 构建插入数据
            data = [
                [str(uuid.uuid4()) for _ in chunks],  # id
                chunks,                                 # text
                [source] * len(chunks),                 # source
                [category] * len(chunks),               # category
                embeddings,                             # vector
            ]

            collection.insert(data)
            collection.flush()
            logger.info(f"KB document added: {len(chunks)} chunks from '{source}'")
            return len(chunks)
        except Exception as e:
            logger.error(f"KB add document failed: {e}")
            return 0

    def _chunk_text(self, text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> List[str]:
        """文本分块。

        优先使用 langchain_text_splitters 1.0+ 的 RecursiveCharacterTextSplitter，
        支持中英文多级分隔符递归分割（段落 → 句子 → 字符），
        在分隔符处自然断句，避免硬截断单词/句子。
        若 langchain_text_splitters 未安装，降级为简单滑动窗口分块。
        """
        if not text:
            return []

        # 优先使用 langchain RecursiveCharacterTextSplitter
        if self._splitter:
            return self._splitter.split_text(text)

        # 降级方案：简单滑动窗口
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap
        return chunks

    async def search(
        self,
        query: str,
        top_k: int = 5,
        category: str = "",
    ) -> List[Dict[str, Any]]:
        """检索知识库文档。

        Args:
            query: 查询文本
            top_k: 返回前 K 条
            category: 限定文档类别（空=不限）

        Returns:
            检索结果列表，每项包含 text/source/category/score
        """
        if not self._connected or not self._client:
            return []

        try:
            from pymilvus import Collection

            collection = Collection(_COLLECTION_NAME, using=self._milvus_alias)
            collection.load()

            # 查询向量化
            query_vector = await self.embedding_service.embed_async(query)
            if not query_vector:
                return []

            # 向量检索
            search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
            expr = f'category == "{category}"' if category else ""

            results = collection.search(
                data=[query_vector],
                anns_field="vector",
                param=search_params,
                limit=top_k,
                expr=expr,
                output_fields=["text", "source", "category"],
            )

            # 格式化结果
            docs = []
            for hit in results[0]:
                entity = hit.entity.get("text", "")
                docs.append({
                    "text": entity,
                    "source": hit.entity.get("source", ""),
                    "category": hit.entity.get("category", ""),
                    "score": float(hit.score),
                })

            return docs
        except Exception as e:
            logger.error(f"KB search failed: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """获取知识库统计信息。"""
        if not self._connected or not self._client:
            return {"connected": False, "total_docs": 0}

        try:
            from pymilvus import Collection

            collection = Collection(_COLLECTION_NAME, using=self._milvus_alias)
            collection.flush()
            stats = {
                "connected": True,
                "collection": _COLLECTION_NAME,
                "total_docs": collection.num_entities,
            }
            return stats
        except Exception as e:
            logger.error(f"KB stats failed: {e}")
            return {"connected": True, "error": str(e)}
