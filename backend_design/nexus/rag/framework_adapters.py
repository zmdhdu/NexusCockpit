# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Framework Adapters — 开源框架组件适配层

用 langchain-openai OpenAIEmbeddings 替代手写 EmbeddingService。
向量存储、图谱存储、检索器、上下文压缩分别由各自的模块直接使用框架组件实现，
不再在此文件统一封装。

已安装框架包:
  langchain-openai 1.1.7      → OpenAIEmbeddings, ChatOpenAI
  langchain-milvus 0.4.0     → Milvus
  langchain-community 0.4.2  → Neo4jGraph, BM25Retriever
  langchain-core 1.5.3       → trim_messages, BaseCache
"""

from __future__ import annotations

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 全局单例缓存
_embeddings = None


def get_langchain_embeddings():
    """获取 LangChain OpenAIEmbeddings 实例（全局单例）。

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


def reset_framework_adapters():
    """重置框架适配器单例（用于配置热更新）。"""
    global _embeddings
    _embeddings = None
    logger.info("Framework adapter singletons reset")
