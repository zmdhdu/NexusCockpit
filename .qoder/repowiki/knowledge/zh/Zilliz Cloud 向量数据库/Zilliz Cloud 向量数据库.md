---
kind: external_dependency
name: Zilliz Cloud 向量数据库
slug: zilliz-cloud
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### Zilliz Cloud 向量数据库
- **角色**：Milvus 官方云托管服务，提供生产级向量检索能力
- **集成点**：通过 MILVUS_URI 和 MILVUS_TOKEN 配置，复用 pymilvus SDK 客户端
- **部署模式**：VECTOR_STORE_PROVIDER=cloud 时自动切换到云端，与本地 Milvus 完全兼容
- **关键特性**：无需运维基础设施、弹性伸缩、与本地 Milvus 代码零差异