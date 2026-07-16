---
kind: external_dependency
name: RabbitMQ — 消息队列（预留未落地）
slug: rabbitmq
category: external_dependency
category_hints:
    - vendor_identity
    - migration_status
scope:
    - '**'
---

### 供应商身份
RabbitMQ 3.13 AMQP 标准消息代理，提供可靠的消息传递和任务队列能力。

### 在本项目中的角色
- **预留功能**：配置了完整的 RabbitMQConfig 和 Celery/Kombu 依赖
- **计划用途**：处理耗时操作如批量 Embedding 生成、异步任务调度

### 当前状态
虽然基础设施已就绪（docker-compose 中包含 RabbitMQ 容器），但代码中**未发现任何 Celery worker 定义或 RabbitMQ 消费者实现**。属于预留但未落地的功能。

### 约束条件
- 默认账号 guest/guest，生产环境必须修改
- 管理界面：http://localhost:15672
- 如果不需要异步任务功能，可从 docker-compose.yml 中移除以减少资源占用