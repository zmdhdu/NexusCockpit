---
kind: external_dependency
name: Redis Stack 缓存与向量搜索
slug: redis-stack
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

### Redis Stack 缓存与向量搜索
- **角色**：语义缓存、滑动窗口限流、Pub/Sub 消息、多座舱数据隔离
- **集成点**：`backend_design/nexus/middleware/redis_cache.py` 语义缓存，`rate_limiter.py` 限流器，多座舱 DB 分区
- **约束**：Windows 开发环境端口映射到 16379 避开保留范围，MaxMemory 策略 allkeys-lru，保护模式关闭便于调试