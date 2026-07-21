---
kind: external_dependency
name: Milvus 向量数据库
slug: milvus
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

### Milvus 向量数据库
- **角色**：语义记忆存储与相似度检索，支撑 GraphRAG 的向量路径检索
- **集成点**：`backend_design/nexus/rag/vector_store.py` 中的 MilvusVectorStore 类，通过 pymilvus SDK 连接
- **双模式部署**：本地 Docker (milvusdb/milvus:v2.4.0) 或云端 Zilliz Cloud，通过 VECTOR_STORE_PROVIDER 配置切换
- **约束**：需配合 etcd 和 MinIO 运行，集合维度必须与 EMBEDDING_DIM 配置匹配，切换 embedding 模型时需重建集合