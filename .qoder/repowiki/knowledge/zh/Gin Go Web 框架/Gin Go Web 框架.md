---
kind: external_dependency
name: Gin Go Web 框架
slug: gin
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

### Gin Go Web 框架
- **角色**: Go 并发网关核心框架，处理高并发非 AI 请求和反向代理
- **集成点**: `backend_design/nexus_gate/cmd/main.go` 作为 HTTP 服务器入口
- **关键职责**: JWT 鉴权、座舱级令牌桶限流、WebSocket Hub、Python 后端反向代理
- **性能特性**: gorilla/websocket 支持千级并发连接、低内存占用
- **架构定位**: 前置网关层，保护 Python AI 服务免受直接外部访问