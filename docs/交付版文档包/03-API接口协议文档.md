# NexusCockpit API 参考文档

> 版本: 2.2.0 | 生成方式: 静态导出 + FastAPI /docs 交互式
> 在线文档: http://localhost:8000/docs (Swagger UI) | http://localhost:8000/redoc (ReDoc)

---

## 概述

NexusCockpit 后端基于 FastAPI 构建，提供 REST + SSE + WebSocket 三种 API 模式。

### 基础信息

| 项目 | 值 |
|------|-----|
| Base URL | `http://localhost:8000` (直连) / `http://localhost:8080` (经 Go 网关) |
| API 版本 | v2.2.0 |
| 认证方式 | Bearer Token (JWT) |
| Content-Type | `application/json` |
| 交互式文档 | `/docs` (Swagger) / `/redoc` (ReDoc) |

### 认证

所有需要认证的接口在请求头中携带 JWT Token:

```
Authorization: Bearer <your_jwt_token>
```

Token 通过 Go 网关 `/auth/login` 接口获取。

---

## API 端点目录

### 认证 (`/auth`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 用户登录，获取 JWT Token |

### 对话 (`/chat`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 文本对话 (非流式) |
| POST | `/chat/stream` | 文本对话 (SSE 流式) |

### 会话管理 (`/chat/sessions`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/chat/sessions` | 获取会话列表 |
| GET | `/chat/sessions/{session_id}` | 获取会话详情 |
| DELETE | `/chat/sessions/{session_id}` | 删除会话 |

### 车控 (`/vehicle`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/vehicle/status` | 获取车辆状态 |
| POST | `/vehicle/control` | 执行车控指令 |

### 座舱 (`/cockpit`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/cockpit/list` | 获取座舱列表 |
| GET | `/cockpit/{cockpit_id}` | 获取座舱详情 |

### 设置 (`/settings`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/settings` | 获取系统设置 |

### 管理后台 (`/admin`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/users` | 用户列表 |
| POST | `/admin/users` | 创建用户 |
| GET | `/admin/cockpits` | 座舱管理 |

### 数据中台 (`/dataplatform`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/dataplatform/overview` | 数据总览 |
| GET | `/dataplatform/concurrency` | 并发指标 |
| GET | `/dataplatform/alerts` | 告警历史 |

### 中间件状态 (`/middleware`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/middleware/` | 所有中间件状态 |
| GET | `/middleware/{name}` | 单个中间件状态 |

### 健康检查 (`/health`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |

### 语音识别 (`/asr`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/asr/recognize` | 语音识别 |

### WebSocket (`/ws`)

| 路径 | 说明 |
|------|------|
| `ws://localhost:8000/ws/chat` | WebSocket 对话 |

### 指标 (`/metrics`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/metrics` | Prometheus 指标端点 |

---

## 核心接口详情

### POST /chat — 文本对话 (非流式)

**请求体**:
```json
{
  "text": "帮我打开车窗",
  "user_id": "user_01",
  "session_id": "session_xxx"
}
```

**响应**:
```json
{
  "response": "好的，已为您打开车窗",
  "user_id": "user_01",
  "session_id": "session_xxx",
  "latency_ms": 1200.5,
  "metadata": {"supervisor_latency_ms": 50.2},
  "intent": "vehicle_control",
  "action": "vehicle_window_open",
  "trace_id": "trace_xxx",
  "cache_hit": false
}
```

### POST /chat/stream — 文本对话 (SSE 流式)

**请求体**: 同 `/chat`

**SSE 事件流**:
```
data: {"type": "thinking", "data": {"message": "正在思考..."}}

data: {"type": "intent", "data": {"intent": "vehicle_control", "source": "heuristic"}}

data: {"type": "experts", "data": {"experts": ["vehicle"]}}

data: {"type": "action", "data": {"action": "vehicle_window_open"}}

data: {"type": "chunk", "data": {"chunk": "好的，已为您打开车窗"}}

data: {"type": "done", "data": {"response": "好的，已为您打开车窗", "latency_ms": 800, "intent": "vehicle_control", "action": "vehicle_window_open"}}
```

---

## 导出说明

### 交互式文档

FastAPI 自动生成交互式 API 文档:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 静态导出

运行以下命令导出静态 OpenAPI schema:

```bash
cd backend_design
python -m scripts.export_openapi
```

输出文件:
- `docs/api/openapi.json` — OpenAPI 3.1 JSON
- `docs/api/openapi.yaml` — OpenAPI 3.1 YAML
- `docs/api/API_REFERENCE.md` — Markdown 文档
