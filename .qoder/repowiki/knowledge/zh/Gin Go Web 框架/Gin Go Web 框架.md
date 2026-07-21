---
kind: external_dependency
name: Gin Go Web 框架
slug: gin
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### Gin Go Web 框架
- **角色**：Go 并发网关核心 Web 框架，处理高并发请求、JWT 鉴权、CORS、反向代理
- **集成点**：`backend_design/nexus_gate/internal/router/router.go` 路由分发，handlers 包处理非 AI 请求
- **使用模式**：轻量级高性能 HTTP 服务器，gorilla/websocket 支持 WebSocket Hub，prometheus/client_golang 暴露指标
- **关键特性**：支持 NoRoute 兜底反代到 Python 后端，优先级令牌桶限流，JWT 中间件鉴权