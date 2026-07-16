---
kind: external_dependency
name: Neo4j 5.x — 图数据库
slug: neo4j
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

### 供应商身份
Neo4j 5.x 开源图数据库，使用 Bolt 协议进行二进制通信，支持 ACID 事务和 Cypher 查询语言。

### 在本项目中的角色
- **用户画像存储**：存储用户的兴趣标签、偏好关系等结构化知识
- **GraphRAG 图谱路径**：基于用户历史对话构建知识图谱，支持关系遍历推理
- **多座舱数据隔离**：v2.1 版本支持按座舱 ID 隔离不同车辆的用户数据

### 集成方式
通过官方 `neo4j` Python 驱动连接，配置项包括：
- `uri="bolt://host:7687"` Bolt 协议地址
- `user/password` 认证信息（默认 neo4j/nexuscockpit）
- 启用 APOC 插件扩展过程库

### 双模式部署
支持本地 Docker 部署和 Neo4j AuraDB 云托管，通过 `GRAPH_STORE_PROVIDER` 环境变量切换。

### 约束条件
- 当前实现使用同步 Cypher 调用，会阻塞异步事件循环，建议改为 `neo4j.AsyncDriver`
- 默认密码 `nexuscockpit` 在生产环境必须修改
- 需要单独安装并配置 APOC 插件以支持高级图算法