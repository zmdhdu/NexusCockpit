---
kind: external_dependency
name: Prometheus + Grafana 监控系统
slug: prometheus-grafana
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### Prometheus + Grafana 监控系统
- **角色**：云原生标准监控方案，采集应用指标、中间件状态、业务 KPI
- **集成点**：Prometheus 采集 Python/Go 服务指标，Grafana 提供可视化看板，Loki 聚合日志
- **部署模式**：Docker Compose 一键部署，预配置 dashboard 和告警规则
- **关键特性**：API 延迟监控、Agent 执行耗时、缓存命中率、中间件健康状态可视化