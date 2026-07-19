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
- **角色**: 语义缓存、限流器、会话存储、指标采集的多功能中间件
- **集成点**: `backend_design/nexus/middleware/redis_cache.py` 语义缓存 + 限流器
- **关键特性**: RediSearch KNN 向量索引、多座舱 DB 分区隔离、滑动窗口限流
- **端口映射**: 宿主机 16379 → 容器 6379（避开 Windows Hyper-V 保留端口）
- **降级策略**: 云 Redis 无 RediSearch 时自动降级为 scan 模式