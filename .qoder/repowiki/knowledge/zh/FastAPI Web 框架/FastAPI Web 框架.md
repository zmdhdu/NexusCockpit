---
kind: external_dependency
name: FastAPI Web 框架
slug: fastapi
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

### FastAPI Web 框架
- **角色**: Python 后端主框架，提供 REST API、SSE、WebSocket 支持
- **集成点**: `backend_design/nexus/main.py` 中创建 FastAPI 应用实例，注册所有路由和中间件
- **使用模式**: 基于装饰器的声明式路由定义，自动 Swagger 文档生成，异步原生支持
- **关键特性**: CORS 中间件、异常处理器、生命周期管理（lifespan）、静态文件挂载