---
kind: external_dependency
name: Redis Stack 7.2 — 缓存与向量搜索
slug: redis-stack
category: external_dependency
category_hints:
    - vendor_identity
    - framework_behavior
scope:
    - '**'
---

### 供应商身份
Redis Stack 7.2 在 Redis 基础上集成了 RediSearch、JSON、Vector Search 等模块，提供单一服务的多种能力。

### 在本项目中的角色
- **语义缓存**：基于向量相似度的回答缓存，减少重复 LLM 调用成本
- **令牌桶限流**：Redis 原子操作实现滑动窗口限流器
- **Pub/Sub 消息队列**：SubAgent 监控告警到 MainAgent 确认层的实时通知
- **会话状态存储**：LangGraph checkpoint 的临时状态缓存

### 集成方式
通过 `redis-py` 客户端连接，关键配置：
- `cache_enabled` 开关语义缓存功能
- `cache_similarity_threshold=0.92` 相似度阈值
- `cache_ttl=3600` 缓存过期时间（秒）
- 多座舱 DB 分区：cockpit-01→DB1, cockpit-02→DB2, cockpit-03→DB3

### 框架行为
- 使用 RediSearch 的 VECTOR 字段创建 FLAT 索引进行精确 KNN 搜索
- 当云 Redis 无 RediSearch 模块时自动降级为 scan 模式（性能较差）
- 向量维度硬编码 `_VECTOR_DIM=1024` 与实际 Embedding 模型输出 2560 维不匹配，导致语义缓存功能可能从未正常工作

### 约束条件
- 默认端口 6379，但 docker-compose 映射到宿主机 16379 以避免 Windows Hyper-V 端口冲突
- 最大内存 512MB，采用 allkeys-lru 淘汰策略