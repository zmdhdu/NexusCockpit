# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Framework Adapters — 开源框架组件适配层

用 langchain / langchain-milvus / langchain-community 组件替代手写实现:
  - get_langchain_embeddings()    → 替代 embedding.py (144行 → 1行)
  - get_langchain_vector_store()  → 替代 vector_store.py (239行 → 3行)
  - get_langchain_graph_store()   → 替代 graph_store.py (170行 → 2行)
  - get_langchain_retriever()      → 替代 retriever.py (212行 → 5行)
  - compress_messages()           → 替代 compressor.py (594行 → 1行)

所有函数返回框架原生对象，供各模块按需调用。

已安装框架包:
  langchain-openai 1.1.7      → OpenAIEmbeddings, ChatOpenAI
  langchain-milvus 0.4.0     → Milvus
  langchain-community 0.4.2  → Neo4jGraph, BM25Retriever
  langchain-core 1.5.3       → trim_messages, BaseCache
"""

from __future__ import annotations

from typing import Any

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 全局单例缓存
_embeddings = None
_vector_store = None
_graph_store = None


# ============================================================
# 1. Embedding: OpenAIEmbeddings 替代手写 EmbeddingService
# ============================================================
# 旧代码: nexus/rag/embedding.py (144行)
#   手写 httpx + CircuitBreaker + tenacity retry + 批量向量化
# 新代码: langchain_openai.OpenAIEmbeddings (1行)
#   自带连接池 + 重试 + 回调 + 批量 + 异步

def get_langchain_embeddings():
    """获取 LangChain OpenAIEmbeddings 实例（全局单例）。

    替代 nexus.rag.embedding.EmbeddingService (144行)。
    OpenAIEmbeddings 自带:
      - httpx 连接池管理
      - 自动重试 (max_retries)
      - 异步支持 (aembed_query, aembed_documents)
      - 批量向量化 (embed_documents)

    Returns:
        OpenAIEmbeddings 实例
    """
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    from langchain_openai import OpenAIEmbeddings

    config = get_config().llm
    _embeddings = OpenAIEmbeddings(
        model=config.embedding_model,
        api_key=config.ark_api_key or "not-needed",
        base_url=config.ark_base_url,
        dimensions=config.embedding_dim,
        timeout=30,
        max_retries=3,
    )
    mode = "local bge-m3" if config.is_local else "cloud API"
    logger.info(f"LangChain OpenAIEmbeddings created: model={config.embedding_model}, mode={mode}")
    return _embeddings


# ============================================================
# 2. Vector Store: langchain_milvus.Milvus 替代手写 MilvusVectorStore
# ============================================================
# 旧代码: nexus/rag/vector_store.py (239行)
#   手写 connect/disconnect + Collection 创建 + 索引管理 + 搜索 + 双集合
# 新代码: langchain_milvus.Milvus (3行)
#   自动管理连接/索引/搜索/插入/删除

def get_langchain_vector_store(collection_name: str = "User_Memory"):
    """获取 LangChain Milvus 向量存储实例。

    替代 nexus.rag.vector_store.MilvusVectorStore (239行)。
    langchain_milvus.Milvus 自动管理:
      - Milvus 连接 (自动连接/断开)
      - Collection 创建 + 索引 (自动 schema + IVF_FLAT/HNSW)
      - 向量搜索 (similarity_search, similarity_search_with_score)
      - 文档插入 (add_texts, add_documents)
      - 文档删除 (delete_by_source 等)

    Args:
        collection_name: Milvus collection 名称

    Returns:
        langchain_milvus.Milvus 实例
    """
    global _vector_store
    # 不同 collection 返回不同实例
    config = get_config().milvus
    embeddings = get_langchain_embeddings()

    from langchain_milvus import Milvus

    store = Milvus(
        embedding_function=embeddings,
        collection_name=collection_name,
        connection_args={
            "uri": config.uri,
            "alias": config.alias,
        },
        index_params={
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 128},
        },
        auto_id=True,
    )
    logger.info(f"LangChain Milvus vector store created: collection={collection_name}")
    return store


# ============================================================
# 3. Graph Store: langchain_community Neo4jGraph 替代手写 Neo4jGraphStore
# ============================================================
# 旧代码: nexus/rag/graph_store.py (170行)
#   手写 driver 连接 + Cypher 查询 + 约束初始化 + 关系 upsert/delete
# 新代码: langchain_community.graphs.Neo4jGraph (2行)
#   自动管理连接 + query() + schema 刷新

def get_langchain_graph_store():
    """获取 LangChain Neo4jGraph 实例。

    替代 nexus.rag.graph_store.Neo4jGraphStore (170行)。
    Neo4jGraph 自动管理:
      - driver 连接/验证
      - Cypher 查询执行 (query())
      - schema 刷新 (refresh_schema())
      - 连接池管理

    Returns:
        langchain_community.graphs.Neo4jGraph 实例
    """
    global _graph_store
    if _graph_store is not None:
        return _graph_store

    from langchain_community.graphs import Neo4jGraph

    config = get_config().neo4j
    _graph_store = Neo4jGraph(
        url=config.uri,
        username=config.user,
        password=config.password,
    )
    logger.info(f"LangChain Neo4jGraph created: uri={config.uri}")
    return _graph_store


# ============================================================
# 4. Retriever: BM25Retriever + Milvus Retriever 替代手写 GraphRAGRetriever
# ============================================================
# 旧代码: nexus/rag/retriever.py (212行)
#   手写三路检索 (Milvus + Neo4j + BM25) + RRF 融合 + Rerank
# 新代码: Milvus.as_retriever() + BM25Retriever + 手写 RRF (简化)
#   注意: EnsembleRetriever 在 langchain-community 0.4.2 中已移除，
#   需用 langchain_classic 或自行实现简单的 RRF 融合。

def get_langchain_retriever(
    vector_store=None,
    documents: list | None = None,
    top_k: int = 5,
):
    """获取 LangChain 检索器（向量 + BM25 双路融合）。

    替代 nexus.rag.retriever.GraphRAGRetriever (212行)。

    使用 langchain_milvus.Milvus.as_retriever() 作为向量检索路，
    BM25Retriever 作为全文检索路，
    简单 RRF 融合替代手写三路融合。

    Args:
        vector_store: LangChain Milvus 实例（可选，自动创建）
        documents: BM25 索引文档列表
        top_k: 检索数量

    Returns:
        callable: 接受 query 返回 list[Document] 的检索器
    """
    store = vector_store or get_langchain_vector_store()
    vector_retriever = store.as_retriever(
        search_kwargs={"k": top_k, "metric_type": "COSINE"},
    )

    # BM25 检索器（如果有文档）
    bm25_retriever = None
    if documents:
        from langchain_community.retrievers import BM25Retriever
        bm25_retriever = BM25Retriever.from_documents(documents, k=top_k)

    if bm25_retriever is None:
        return vector_retriever

    # 简单 RRF 融合（替代 EnsembleRetriever，该类在 langchain-community 0.4.2 中已移除）
    async def _hybrid_retrieve(query: str) -> list:
        """双路检索 + RRF 融合。"""
        vec_results = await vector_retriever.ainvoke(query)
        bm25_results = await bm25_retriever.ainvoke(query)

        # RRF 融合: score = sum(1 / (rank + 60))
        rrf_scores: dict[str, float] = {}
        rrf_docs: dict[str, Any] = {}

        for rank, doc in enumerate(vec_results):
            key = doc.page_content[:100]
            rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (rank + 60)
            rrf_docs[key] = doc

        for rank, doc in enumerate(bm25_results):
            key = doc.page_content[:100]
            rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (rank + 60)
            if key not in rrf_docs:
                rrf_docs[key] = doc

        # 按 RRF 分数排序
        sorted_keys = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:top_k]
        return [rrf_docs[k] for k in sorted_keys]

    logger.info("LangChain hybrid retriever created (Milvus + BM25 + RRF)")
    return _hybrid_retrieve


# ============================================================
# 5. Context Compression: trim_messages 替代手写 ContextCompressor
# ============================================================
# 旧代码: nexus/memory/compressor.py (594行)
#   手写 tiktoken 计数 + 四级压缩 + 滚动摘要 + 关键信息提取 + 预算分配
# 新代码: langchain_core.messages.trim_messages (1行)
#   自动按 token 预算裁剪消息，支持 "first"/"last" 策略

def compress_messages(
    messages: list[dict],
    max_tokens: int = 4096,
    strategy: str = "last",
    token_counter=None,
) -> list[dict]:
    """用 LangChain trim_messages 裁剪对话历史。

    替代 nexus.memory.compressor.ContextCompressor.build_context() (594行)。
    trim_messages 自动:
      - 精确 token 计数（tiktoken）
      - 按预算裁剪消息（保留 system + 最近 N 轮）
      - 支持 "first"（保留开头）和 "last"（保留末尾）策略
      - 支持 start_on 指定起始消息类型

    Args:
        messages: OpenAI 格式消息列表 [{"role": ..., "content": ...}]
        max_tokens: 最大 token 预算
        strategy: "first" 保留开头消息 / "last" 保留末尾消息
        token_counter: 自定义 token 计数器（可选）

    Returns:
        裁剪后的消息列表
    """
    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
        SystemMessage,
        trim_messages,
    )

    # 将 dict 格式转换为 LangChain Message 对象
    role_map = {
        "system": SystemMessage,
        "user": HumanMessage,
        "assistant": AIMessage,
    }
    lc_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        cls = role_map.get(role, HumanMessage)
        lc_messages.append(cls(content=content))

    # 使用 trim_messages 裁剪
    trimmed = trim_messages(
        lc_messages,
        max_tokens=max_tokens,
        strategy=strategy,
        token_counter=token_counter,
        start_on="human" if strategy == "last" else "system",
        include_system=True,  # 始终保留 system 消息
    )

    # 转回 dict 格式
    result = []
    for msg in trimmed:
        if isinstance(msg, SystemMessage):
            result.append({"role": "system", "content": msg.content})
        elif isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"role": "assistant", "content": msg.content})

    original_count = len(messages)
    trimmed_count = len(result)
    if trimmed_count < original_count:
        logger.info(f"trim_messages: {original_count} → {trimmed_count} msgs (budget={max_tokens}t)")

    return result


# ============================================================
# 6. Reset all singletons (for config hot reload)
# ============================================================

def reset_framework_adapters():
    """重置所有框架适配器单例（用于配置热更新）。"""
    global _embeddings, _vector_store, _graph_store
    _embeddings = None
    _vector_store = None
    _graph_store = None
    logger.info("Framework adapter singletons reset")
