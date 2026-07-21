---
kind: external_dependency
name: Neo4j 知识图谱数据库
slug: neo4j
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

### Neo4j 知识图谱数据库
- **角色**：用户画像与关系图谱存储，支撑 GraphRAG 的图谱路径检索
- **集成点**：`backend_design/nexus/rag/graph_store.py` 中的 Neo4jGraphStore 类，通过 neo4j Python driver 连接
- **约束**：需启用 APOC 插件以支持高级图算法，AuraDB 使用 neo4j+s 加密协议，密码通过环境变量注入