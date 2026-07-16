---
kind: external_dependency
name: Milvus 2.4 — 开源向量数据库
slug: milvus
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

### 供应商身份
Milvus 2.4 开源向量数据库，由 Zilliz 公司维护，支持分布式部署和高性能向量相似度搜索。

### 在本项目中的角色
- **食物知识库存储**：Food_List collection 存储食物相关文本的语义向量
- **用户记忆存储**：User_Memory collection 存储用户偏好和历史记忆的向量表示
- **GraphRAG 向量路径**：与 Neo4j 图谱路径、BM25 全文路径三路融合召回

### 集成方式
通过 `pymilvus` SDK 连接，配置项包括：
- `host/port/uri/token` 连接参数
- `collection_food/collection_memory` collection 名称
- `index_type="HNSW"` + `metric_type="IP"`（内积用于余弦相似度）
- HNSW 索引参数：`M=16, efConstruction=200`，搜索参数：`ef=64`

### 双模式部署
支持本地 Docker 部署和 Zilliz Cloud 托管两种模式，通过 `VECTOR_STORE_PROVIDER` 环境变量切换。

### 约束条件
- 默认使用 IP（内积）距离度量，要求输入向量已归一化
- HNSW 索引的内存占用与向量维度正相关（当前 2560 维 × float32 = 10KB/条）
- 需要 etcd 和 MinIO 作为依赖组件（docker-compose 中已编排）