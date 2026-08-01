# L6 API 层 (API Gateway)

> 对应代码: `nexus/api/` + `nexus/main.py`
> 最后更新: 2026-07-14

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
| `/` | GET | 根路径返回项目信息 |
| `/health` | GET | 健康检查 |
| `/chat` | POST | 文本对话 (非流式) |
| `/chat/stream` | POST | 文本对话 (SSE 流式，含心跳+断开检测) |
| `/chat/sessions` | GET | 获取当前座舱的会话列表 |
| `/chat/sessions` | POST | 创建新会话 |
| `/chat/sessions/{id}` | DELETE | 删除会话及其消息记录 |
| `/chat/sessions/{id}/messages` | GET | 获取会话消息记录 |
| `/vehicle/command` | POST | 车控命令 (JWT 认证) |
| `/vehicle/status` | GET | 车辆状态查询 (JWT 认证) |
| `/cockpit/{cockpit_id}/status` | GET | 座舱状态查询 (v2.1) |
| `/cockpit/{cockpit_id}/chat` | POST | 座舱级文本对话 (v2.1) |
| `/cockpit/{cockpit_id}/chat/stream` | POST | 座舱级 SSE 流式 (v2.1) |
| `/cockpit/{cockpit_id}/vehicle/cmd` | POST | 座舱级车控命令 (v2.1) |
| `/cockpit/{cockpit_id}/vehicle/status` | GET | 座舱级车辆状态 (v2.1) |
| `/auth/token` | POST | JWT 令牌签发 |
| `/auth/me` | GET | 当前用户信息 (JWT 认证) |
| `/auth/change-password` | POST | 修改密码 (JWT 认证) |
| `/admin/skills` | GET | 技能列表 (JWT 认证) |
| `/admin/cache/stats` | GET | 缓存统计 (JWT 认证) |
| `/admin/cache/clear` | POST | 清空缓存 (JWT 认证) |
| `/admin/sessions` | GET | 会话列表 (JWT 认证) |
| `/admin/memory/{user_id}` | GET | 用户记忆查询 (JWT 认证) |
| `/admin/kb/upload` | POST | 知识库上传 (JWT 认证) |
| `/admin/kb/reindex` | POST | 知识库重建索引 (JWT 认证) |
| `/admin/kb/stats` | GET | 知识库统计 (JWT 认证) |
| `/settings/cockpits` | GET/POST | 座舱管理 (v2.1) |
| `/settings/cockpits/{id}` | PUT/DELETE | 座舱修改/删除 (v2.1) |
| `/settings/users` | GET/POST | 用户管理 (v2.1) |
| `/settings/users/{id}` | DELETE | 用户删除 (v2.1) |
| `/settings/middleware` | GET/PUT | 中间件配置 (v2.1) |
| `/settings/voiceprint/status` | GET | 声纹状态 (v2.1) |
| `/settings/voiceprint/enroll` | POST | 声纹注册 (v2.1) |
| `/settings/voiceprint/verify` | POST | 声纹验证 (v2.1) |
| `/dataplatform/overview` | GET | 数据中台概览 (v2.1) |
| `/dataplatform/cockpit/{id}` | GET | 座舱详情 (v2.1) |
| `/dataplatform/concurrency` | GET | 并发监控 (v2.1) |
| `/dataplatform/alerts` | GET | 告警历史 (v2.1) |
| `/dataplatform/agent/activity` | GET | Agent 活动统计 (v2.1) |
| `/dataplatform/comparison` | GET | 座舱对比 (v2.1) |
| `/middleware` | GET | 中间件状态汇总 (v2.1) |
| `/middleware/redis` | GET | Redis 状态 (v2.1) |
| `/middleware/milvus` | GET | Milvus 状态 (v2.1) |
| `/middleware/neo4j` | GET | Neo4j 状态 (v2.1) |
| `/middleware/rabbitmq` | GET | RabbitMQ 状态 (v2.1，已废弃) |
| `/middleware/mysql` | GET | MySQL 状态 (v2.1) |
| `/asr/transcribe` | POST | 语音识别 (v2.1) |
| `/asr/status` | GET | ASR 引擎状态 (v2.1) |
| `/ws/chat` | WS | WebSocket 实时通信 (JWT via query param) |
| `/metrics` | GET | Prometheus 指标 |
| `/audio/{path}` | GET | 静态音频文件 |
| `/docs` | GET | Swagger 文档 |

## MCP 服务层接口

MCP (Model Context Protocol) 网关 (`nexus/mcp/gateway.py`) 提供统一工具调用入口，封装车控适配器，支持工具发现与调用：

```python
from nexus.mcp.gateway import MCPGateway

gateway = MCPGateway(adapter=vehicle_adapter)
gateway.list_tools()   # → [{"name": "vehicle_climate", "description": "..."}, ...]
gateway.invoke("vehicle_climate", {"op": "set_temp", "target_temp": 24})
```

> **注意**: MCP 网关当前仅作为内部服务层组件被 Agent 层调用，尚未暴露独立的 HTTP 端点。
> 可用工具包括: vehicle_climate / vehicle_window / vehicle_seat / vehicle_navigation / vehicle_media / vehicle_status。
> 详见 [L3-service.md](./L3-service.md) 中的 MCP 网关章节。

## 模块清单

### main.py — FastAPI 应用

```python
from nexus.main import app

# 应用生命周期 (lifespan):
# 1. 加载配置 + 初始化日志 + 初始化 Prometheus 指标
# 2. 初始化 Embedding 服务
# 3. 初始化向量存储 (工厂模式: 本地 Milvus / 云端 Zilliz, 由 VECTOR_STORE_PROVIDER 决定)
# 4. 初始化图谱存储 (工厂模式: 本地 Neo4j / 云端 AuraDB, 由 GRAPH_STORE_PROVIDER 决定)
# 5. 构建车控适配器 (mock/http/mcp)
# 6. v2.2 简化: OSS 对象存储已移除（未集成，过度设计）
# 7. 连接 Redis 语义缓存
# 8. 初始化限流器 (Lua 脚本原子化)
# 9. 初始化会话历史存储 (SessionStore, Redis 持久化)
# 10. 初始化 Langfuse 追踪监控器
# 11. 初始化 Agent 工作流 (SkillRegistry + MemoryManager + IntentRouter + SupervisorGraph)
#
# 注册路由: health / chat / vehicle / auth / admin / ws
# 注册异常处理器: RateLimitError(429) / AuthError(401) / NexusError(500)
```

### routes/chat.py — 聊天 API

```python
# 非流式
POST /chat
{
    "text": "把空调调到24度",
    "user_id": "u1",
    "session_id": "sess_abc123"
}

# 流式 (SSE)
POST /chat/stream
{
    "text": "今天天气怎么样",
    "user_id": "u1",
    "session_id": "sess_abc123",
    "stream": true
}
→ data: {"type": "intent", "data": {"intent": "weather", "source": "llm"}}
→ data: {"type": "experts", "data": {"active": ["chat_expert"]}}
→ data: {"type": "action", "data": {"skill": "web_search", "status": "ok"}}
→ data: {"type": "chunk", "data": {"text": "今天"}}
→ data: {"type": "chunk", "data": {"text": "天气"}}
→ data: {"type": "done", "data": {"response": "今天天气..."}}
```

> **v2.2.4 会话并发锁**: 同一 session_id 的请求通过 `asyncio.Lock` 串行化，
> 防止并发请求交叉污染会话历史。锁上限 500 个，超限时自动清理空闲锁。
>
> **v2.2.5 会话隔离修复**: `session_id` 为空时生成唯一临时 ID（`temp_xxx`），
> 禁止回退到 `user_id`，确保不同对话之间的历史完全隔离。
>
> **v2.2.2 多会话管理**: 支持 POST/GET/DELETE `/chat/sessions` 管理会话，
> 消息记录持久化到 MySQL `chat_logs` 表（按 `cockpit_id` + `session_id` 隔离）。

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

### routes/auth.py — 认证接口

```python
# 获取 JWT 令牌
POST /auth/token
{
    "username": "admin",
    "password": "******"
}
{
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 3600
}

# 查看当前用户
GET /auth/me
Authorization: Bearer eyJ...
{
    "username": "admin"
}
```

### routes/admin.py — 管理接口

提供缓存统计/清空、会话管理、技能列表、用户记忆查询等管理端点。所有端点均需 JWT 认证。

### websocket.py — WebSocket 接口

WebSocket 连接需通过 query 参数传递 JWT 令牌进行认证，并支持心跳机制检测连接健康状态。

```javascript
// 连接时携带 JWT
const ws = new WebSocket("ws://localhost:8000/ws/chat?token=eyJ...");
ws.send(JSON.stringify({text: "导航到上海虹桥", user_id: "u1"}));
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(data);
};
// 心跳: 服务端定期发送 ping，客户端需回复 pong
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
