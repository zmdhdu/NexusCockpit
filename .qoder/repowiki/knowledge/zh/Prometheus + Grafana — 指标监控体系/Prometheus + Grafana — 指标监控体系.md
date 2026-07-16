---
kind: external_dependency
name: Prometheus + Grafana — 指标监控体系
slug: prometheus-grafana
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### 供应商身份
Prometheus 时序数据库 + Grafana 可视化看板，构成云原生标准的监控解决方案。

### 在本项目中的角色
- **系统指标采集**：API 延迟、Agent 执行耗时、缓存命中率等核心业务指标
- **中间件监控**：Milvus、Neo4j、Redis、RabbitMQ、MySQL 等基础设施运行状态
- **自定义指标**：通过 `prometheus-client` SDK 暴露 Python 应用的自定义 metrics

### 集成方式
- Prometheus 配置：`config/prometheus/prometheus.yml` 定义 scrape targets
- Grafana 预配置：`config/grafana/provisioning/` 自动导入仪表盘和数据源
- 默认账号：admin/admin（生产环境必须修改）

### 约束条件
- Prometheus 端口 9090，Grafana 端口 3001（映射到宿主机）
- Loki 日志聚合服务（端口 3100）配合使用实现日志-指标联动分析
- 需要定期清理历史数据避免磁盘空间耗尽