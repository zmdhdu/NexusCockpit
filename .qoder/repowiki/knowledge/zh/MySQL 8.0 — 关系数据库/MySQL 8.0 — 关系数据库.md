---
kind: external_dependency
name: MySQL 8.0 — 关系数据库
slug: mysql
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

### 供应商身份
MySQL 8.0 关系型数据库，使用 utf8mb4 字符集支持中文和多语言。

### 在本项目中的角色
- **用户账号管理**：存储用户基本信息、权限角色等核心业务数据
- **会话历史持久化**：保存对话记录、操作日志等审计数据
- **多座舱数据隔离**：v2.1 版本支持严格隔离模式（每座舱独立数据库）

### 集成方式
通过 `aiomysql` 异步驱动连接，配置项包括：
- `host/port/user/database` 连接参数
- `charset=utf8mb4` 字符集设置
- 启动时自动执行 `v2.1_migration.sql` 迁移脚本

### 约束条件
- 默认密码 `nexuscockpit`，生产环境必须修改
- 默认端口 3306，但 docker-compose 映射到宿主机 13306 避让本机已安装的 MySQL
- 使用原生密码认证插件 `mysql_native_password` 保证兼容性