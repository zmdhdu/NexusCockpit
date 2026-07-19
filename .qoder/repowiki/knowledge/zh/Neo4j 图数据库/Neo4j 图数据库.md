---
kind: external_dependency
name: Neo4j 图数据库
slug: neo4j
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

### Neo4j 图数据库
- **角色**: 知识图谱存储，支撑 GraphRAG 的图谱路径和用户画像关系遍历
- **集成点**: `backend_design/nexus/rag/graph_factory.py` 支持本地/云端 AuraDB 切换
- **双模式部署**: local=本地 Docker Neo4j 5.19 | cloud=Neo4j AuraDB 托管服务
- **关键配置**: Bolt 协议连接、APOC 插件启用、ACID 事务支持
- **数据模型**: 用户偏好、技能关系、车控设备关系的图结构存储