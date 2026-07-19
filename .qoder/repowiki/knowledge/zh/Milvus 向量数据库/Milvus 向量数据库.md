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
- **角色**: 语义向量存储与检索，支撑 GraphRAG 三路融合检索的向量路径
- **集成点**: `backend_design/nexus/rag/vector_factory.py` 通过工厂模式支持本地/云端切换
- **双模式部署**: local=本地 Docker Milvus 2.4 | cloud=Zilliz Cloud 托管服务
- **关键配置**: HNSW 索引、IP 距离度量、集合命名（Food_List/User_Memory）
- **容器化**: docker-compose.yml 中 etcd + minio + milvus 三组件编排