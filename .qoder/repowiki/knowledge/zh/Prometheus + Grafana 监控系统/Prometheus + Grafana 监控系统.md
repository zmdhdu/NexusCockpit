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
- **角色**: 基础设施和应用性能监控，提供可视化看板
- **集成点**: `backend_design/nexus/observability/metrics.py` Prometheus 指标导出
- **监控范围**: API 延迟、Agent 执行耗时、缓存命中率、中间件状态
- **容器编排**: docker-compose.yml 中 prometheus + grafana + loki 日志聚合
- **访问地址**: Grafana http://localhost:3001 (admin/admin)