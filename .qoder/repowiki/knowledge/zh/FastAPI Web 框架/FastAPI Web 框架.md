---
kind: external_dependency
name: FastAPI Web 框架
slug: fastapi
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### FastAPI Web 框架
- **角色**：Python 后端主 Web 框架，提供 REST API、SSE 流式输出、WebSocket 支持
- **集成点**：`backend_design/nexus/main.py` 应用入口，所有路由定义在 `nexus/api/routes/` 下
- **使用模式**：异步原生（async/await），自动 OpenAPI/Swagger 文档生成，Pydantic v2 数据验证
- **关键特性**：与 LangGraph、Redis、Milvus 等生态组件深度集成，支持 SSE 流式响应用于 LLM 对话场景