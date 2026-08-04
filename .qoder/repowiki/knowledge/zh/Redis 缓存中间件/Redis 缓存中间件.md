---
kind: external_dependency
name: Redis 缓存中间件
slug: redis
category: external_dependency
category_hints:
    - migration_status
scope:
    - '**'
source_files:
    - backend_design/nexus/agent/
---

### Redis 缓存中间件
- **角色**: 用于中间件状态管理和会话缓存
- **当前状态**: 在架构简化过程中考虑移除 Redis Checkpoint 分支，简化依赖
- **替代方案**: 使用更轻量级的内存存储或文件持久化方案
- **影响范围**: 涉及会话状态管理和临时数据存储
- **验证**: 需评估移除 Redis 对系统功能的影响