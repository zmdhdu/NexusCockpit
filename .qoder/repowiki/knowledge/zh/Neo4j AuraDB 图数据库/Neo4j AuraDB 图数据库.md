---
kind: external_dependency
name: Neo4j AuraDB 图数据库
slug: neo4j-auradb
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### Neo4j AuraDB 图数据库
- **角色**：Neo4j 官方云托管服务，提供生产级知识图谱能力
- **集成点**：通过 NEO4J_URI (neo4j+s://) 和 NEO4J_PASSWORD 配置，复用 neo4j Python driver
- **部署模式**：GRAPH_STORE_PROVIDER=cloud 时自动切换到云端，使用 TLS 加密连接
- **关键特性**：无需运维基础设施、全球分布、与本地 Neo4j 代码零差异