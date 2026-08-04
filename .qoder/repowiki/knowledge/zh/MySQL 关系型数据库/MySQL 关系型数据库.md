---
kind: external_dependency
name: MySQL 关系型数据库
slug: mysql
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
source_files:
    - config.py
---

### MySQL 关系型数据库
- **角色**: 持久化存储座舱配置、用户画像、技能配置文件等结构化数据
- **集成点**: config.py 中配置数据库连接参数
- **迁移计划**: 将座舱配置从其他存储方式迁移到 MySQL 统一管理
- **企业级要求**: 需要满足车载场景的高可用性和数据一致性要求
- **验证**: 需确认具体的连接配置和数据表结构设计