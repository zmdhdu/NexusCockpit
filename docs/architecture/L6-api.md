# L6 API 层 (API Gateway)

> 对应代码: `nexus/api/` + `nexus/main.py`

## 职责

提供对外 HTTP/WebSocket 接口：
- **REST API** — 文本对话、车控命令、管理接口
- **SSE 流式** — Server-Sent Events 流式响应
- **WebSocket** — 实时双向通信 (语音)
- **JWT 认证** — 用户身份验证
- **全局异常处理** — 统一错误响应格式

## 路由清单

| 路由 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/chat` | POST | 文本对话 (非流式) |
| `/chat/stream` | POST | 文本对话 (SSE 流式) |
| `/vehicle/command` | POST | 车控命令 |
| `/vehicle/status` | GET | 车辆状态查询 |
| `/admin/skills` | GET | 技能列表 |
| `/admin/cache/stats` | GET | 缓存统计 |
| `/admin/sessions` | GET | 会话列表 |
| `/ws/chat` | WS | WebSocket 实时通信 |
| `/metrics` | GET | Prometheus 指标 |
| `/docs` | GET | Swagger 文档 |

## 模块清单

### main.py — FastAPI 应用

```python
from nexus.main import app

# 应用生命周期:
# 1. 加载配置
# 2. 初始化 Embedding 服务
# 3. 连接 Milvus / Neo4j
# 4. 构建车控适配器
# 5. 连接 Redis (缓存 + 限流)
# 6. 初始化 Agent 工作流
```

### routes/chat.py — 聊天 API

```python
# 非流式
POST /chat
{
    "text": "把空调调到24度",
    "user_id": "u1"
}

# 流式 (SSE)
POST /chat/stream
{
    "text": "今天天气怎么样",
    "user_id": "u1",
    "stream": true
}
→ data: {"node": "planner", "data": {"intent": "weather"}}
→ data: {"node": "responder", "data": {"chunk": "今天"}}
→ data: {"node": "responder", "data": {"chunk": "天气"}}
→ data: [DONE]
```

### routes/vehicle.py — 车控 API

```python
POST /vehicle/command
{
    "command": "vehicle_climate",
    "arguments": {"op": "set_temp", "target_temp": 24}
}
→ {"success": true, "result": {"current_temp": 24}}
```

### routes/health.py — 健康检查

```python
GET /health
→ {
    "status": "healthy",
    "services": {
        "milvus": "connected",
        "neo4j": "connected",
        "redis": "connected",
        "agent": "ready"
    }
}
```

### routes/admin.py — 管理接口

提供缓存统计、会话管理、技能列表等管理端点。

### websocket.py — WebSocket 接口

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/chat");
ws.send(JSON.stringify({text: "导航到上海虹桥", user_id: "u1"}));
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(data);
};
```

## 中间件

| 中间件 | 说明 |
|--------|------|
| CORS | 跨域允许 |
| Timing | 请求计时 (X-Response-Time-ms) |
| Exception | 全局异常捕获 |
| Metrics | Prometheus 指标采集 |

## 请求/响应格式

### 统一成功响应

```json
{
    "success": true,
    "data": { ... },
    "trace_id": "uuid"
}
```

### 统一错误响应

```json
{
    "error": "ERROR_CODE",
    "message": "人类可读的错误描述",
    "details": { ... }
}
```

## 设计原则

1. **路由分组** — 按功能模块分文件
2. **依赖注入** — 通过 `app.state` 注入服务实例
3. **统一响应** — 成功和错误使用统一格式
4. **自动文档** — FastAPI 自动生成 OpenAPI 文档
