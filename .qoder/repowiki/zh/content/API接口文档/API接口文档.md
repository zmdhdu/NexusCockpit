# API接口文档

<cite>
**本文引用的文件**   
- [backend_design/nexus/main.py](file://backend_design/nexus/main.py)
- [backend_design/nexus/api/routes/auth.py](file://backend_design/nexus/api/routes/auth.py)
- [backend_design/nexus/api/routes/chat.py](file://backend_design/nexus/api/routes/chat.py)
- [backend_design/nexus/api/routes/chat_sessions.py](file://backend_design/nexus/api/routes/chat_sessions.py)
- [backend_design/nexus/api/routes/cockpit.py](file://backend_design/nexus/api/routes/cockpit.py)
- [backend_design/nexus/api/routes/dataplatform.py](file://backend_design/nexus/api/routes/dataplatform.py)
- [backend_design/nexus/api/routes/health.py](file://backend_design/nexus/api/routes/health.py)
- [backend_design/nexus/api/routes/middleware_status.py](file://backend_design/nexus/api/routes/middleware_status.py)
- [backend_design/nexus/api/routes/settings.py](file://backend_design/nexus/api/routes/settings.py)
- [backend_design/nexus/api/routes/vehicle.py](file://backend_design/nexus/api/routes/vehicle.py)
- [backend_design/nexus/api/websocket.py](file://backend_design/nexus/api/websocket.py)
- [backend_design/nexus/core/auth.py](file://backend_design/nexus/core/auth.py)
- [backend_design/nexus/core/exceptions.py](file://backend_design/nexus/core/exceptions.py)
- [backend_design/nexus/models/schemas.py](file://backend_design/nexus/models/schemas.py)
- [backend_design/nexus_gate/internal/handlers/handlers.go](file://backend_design/nexus_gate/internal/handlers/handlers.go)
- [backend_design/nexus_gate/internal/ws/hub.go](file://backend_design/nexus_gate/internal/ws/hub.go)
- [backend_design/nexus_gate/proto/nexus.proto](file://backend_design/nexus_gate/proto/nexus.proto)
</cite>

## 更新摘要
**变更内容**   
- 统一网关集成：所有API访问通过端口8080的统一网关进行路由
- JWT令牌互操作性：建立Python后端与Go网关之间的JWT令牌互通机制
- WebSocket安全增强：实现CORS白名单验证，提升WebSocket连接安全性
- 架构调整：客户端现在统一通过网关端口8080访问所有服务

## 目录
1. [简介](#简介)
2. [项目结构](#项目结构)
3. [核心组件](#核心组件)
4. [架构总览](#架构总览)
5. [详细组件分析](#详细组件分析)
6. [依赖关系分析](#依赖关系分析)
7. [性能考虑](#性能考虑)
8. [故障排查指南](#故障排查指南)
9. [结论](#结论)
10. [附录](#附录)

## 简介
本文件为 NexusCockpit 系统的完整API接口文档，覆盖以下范围：
- RESTful API端点：HTTP方法、URL路径、请求参数、响应格式与错误码
- WebSocket实时通信：连接建立、消息格式、事件类型与状态管理
- gRPC内部服务契约：protobuf消息与服务定义
- 认证与授权：JWT令牌使用、权限控制与访问限制
- API版本管理与向后兼容策略
- SDK集成指南与客户端最佳实践

**更新** 系统现已采用统一网关架构，所有外部访问必须通过端口8080的NexusGate网关进行。

## 项目结构
后端采用Python FastAPI应用，按功能模块划分路由；网关采用Go实现，提供鉴权、限流、代理与WebSocket转发能力。所有外部客户端现在统一通过网关端口8080访问系统。

```mermaid
graph TB
Client["客户端"] --> Gateway["NexusGate(端口8080)"]
Gateway --> Auth["鉴权/限流/CORS验证"]
Gateway --> Proxy["反向代理"]
Proxy --> App["NexusCockpit(FastAPI)"]
App --> Routes["业务路由<br/>auth/chat/cockpit/..."]
App --> WS["WebSocket处理器"]
App --> Models["数据模型/校验"]
App --> Core["核心能力<br/>鉴权/异常/日志"]
```

**图表来源**
- [backend_design/nexus/main.py](file://backend_design/nexus/main.py)
- [backend_design/nexus/api/websocket.py](file://backend_design/nexus/api/websocket.py)
- [backend_design/nexus_gate/internal/handlers/handlers.go](file://backend_design/nexus_gate/internal/handlers/handlers.go)
- [backend_design/nexus_gate/internal/ws/hub.go](file://backend_design/nexus_gate/internal/ws/hub.go)

**章节来源**
- [backend_design/nexus/main.py](file://backend_design/nexus/main.py)
- [backend_design/nexus/api/websocket.py](file://backend_design/nexus/api/websocket.py)
- [backend_design/nexus_gate/internal/handlers/handlers.go](file://backend_design/nexus_gate/internal/handlers/handlers.go)
- [backend_design/nexus_gate/internal/ws/hub.go](file://backend_design/nexus_gate/internal/ws/hub.go)

## 核心组件
- 路由层：按领域组织REST端点（认证、聊天、座舱、数据平台、健康检查、中间件状态、设置、车辆等）
- 认证与授权：基于JWT的无状态鉴权，结合网关层限流与访问控制
- 数据模型：Pydantic模型用于请求/响应结构与字段校验
- 异常处理：统一异常类型与错误响应格式
- WebSocket：服务端推送与双向通信，支持CORS白名单验证

**更新** 网关层现包含统一的JWT令牌验证和CORS白名单验证机制，确保跨域WebSocket连接的安全性。

**章节来源**
- [backend_design/nexus/api/routes/auth.py](file://backend_design/nexus/api/routes/auth.py)
- [backend_design/nexus/api/routes/chat.py](file://backend_design/nexus/api/routes/chat.py)
- [backend_design/nexus/api/routes/chat_sessions.py](file://backend_design/nexus/api/routes/chat_sessions.py)
- [backend_design/nexus/api/routes/cockpit.py](file://backend_design/nexus/api/routes/cockpit.py)
- [backend_design/nexus/api/routes/dataplatform.py](file://backend_design/nexus/api/routes/dataplatform.py)
- [backend_design/nexus/api/routes/health.py](file://backend_design/nexus/api/routes/health.py)
- [backend_design/nexus/api/routes/middleware_status.py](file://backend_design/nexus/api/routes/middleware_status.py)
- [backend_design/nexus/api/routes/settings.py](file://backend_design/nexus/api/routes/settings.py)
- [backend_design/nexus/api/routes/vehicle.py](file://backend_design/nexus/api/routes/vehicle.py)
- [backend_design/nexus/core/auth.py](file://backend_design/nexus/core/auth.py)
- [backend_design/nexus/core/exceptions.py](file://backend_design/nexus/core/exceptions.py)
- [backend_design/nexus/models/schemas.py](file://backend_design/nexus/models/schemas.py)

## 架构总览
系统由前端、网关与后端组成。网关负责鉴权、限流、协议转换与WebSocket转发；后端提供REST与WebSocket服务，并通过数据模型进行输入输出校验。**更新** 所有外部访问现在统一通过网关端口8080进行，网关实现了Python后端与Go前端的JWT令牌互操作性。

```mermaid
sequenceDiagram
participant C as "客户端"
participant G as "NexusGate(端口8080)"
participant A as "FastAPI应用"
participant R as "路由处理器"
participant M as "数据模型/校验"
participant W as "WebSocket处理器"
C->>G : "HTTP请求(携带JWT)"
G->>G : "JWT验证/CORS检查/限流"
G->>A : "转发到对应路由"
A->>R : "路由处理"
R->>M : "请求体校验/构造响应"
M-->>R : "校验结果/结构化数据"
R-->>G : "JSON响应"
G-->>C : "返回响应"
C->>G : "WS握手(端口8080)"
G->>G : "CORS白名单验证"
G->>W : "升级并转发"
W-->>C : "事件推送/双向消息"
```

**图表来源**
- [backend_design/nexus/main.py](file://backend_design/nexus/main.py)
- [backend_design/nexus/api/websocket.py](file://backend_design/nexus/api/websocket.py)
- [backend_design/nexus_gate/internal/handlers/handlers.go](file://backend_design/nexus_gate/internal/handlers/handlers.go)
- [backend_design/nexus_gate/internal/ws/hub.go](file://backend_design/nexus_gate/internal/ws/hub.go)

## 详细组件分析

### 统一网关接入（端口8080）
**新增** 系统现已采用统一网关架构，所有外部客户端必须通过端口8080访问API服务。

网关主要功能：
- 统一入口：所有HTTP和WebSocket请求都通过端口8080
- JWT令牌验证：验证Python后端签发的JWT令牌有效性
- CORS白名单验证：仅允许配置的域名进行跨域访问
- 请求限流：防止恶意攻击和滥用
- 协议转换：在Go网关和Python后端之间进行必要的协议适配

客户端接入示例：
```javascript
// 旧方式（已废弃）
const directUrl = 'http://localhost:8000/api/v1/chat';

// 新方式（推荐）
const gatewayUrl = 'http://localhost:8080/api/v1/chat';
```

**章节来源**
- [backend_design/nexus_gate/internal/handlers/handlers.go](file://backend_design/nexus_gate/internal/handlers/handlers.go)

### 认证与授权（REST）
- 登录与令牌签发：通过认证路由获取JWT令牌，后续请求在Header中携带令牌
- 令牌校验：核心鉴权模块解析并验证令牌有效性及权限信息
- 访问限制：网关层对敏感接口实施限流与白名单策略
- **更新** JWT令牌现在在Python后端和Go网关之间完全互通

建议的请求头
- Authorization: Bearer <JWT>
- Origin: <允许的域名>

典型流程
- 客户端调用登录接口获取令牌
- 客户端在后续请求中附加Authorization头
- 网关校验令牌与权限后转发至后端路由
- 路由处理器根据用户上下文执行操作

**更新** 网关层现在直接验证JWT令牌，无需每次都转发到后端进行验证，提升了性能。

**章节来源**
- [backend_design/nexus/api/routes/auth.py](file://backend_design/nexus/api/routes/auth.py)
- [backend_design/nexus/core/auth.py](file://backend_design/nexus/core/auth.py)

### 聊天会话（REST）
- 会话创建与管理：支持创建新会话、列出历史会话、删除会话
- 消息发送与接收：提交文本或语音转写内容，返回结构化对话片段
- 分页与过滤：支持按时间、关键词检索与分页查询

请求示例要点
- 会话列表：GET /api/v1/chat/sessions?page=1&size=20
- 创建会话：POST /api/v1/chat/sessions {title}
- 发送消息：POST /api/v1/chat/messages {session_id, content, type}

响应示例要点
- 会话对象包含id、标题、创建时间、最后更新时间
- 消息对象包含id、会话id、角色、内容、时间戳

**更新** 所有API端点现在通过网关端口8080访问

**章节来源**
- [backend_design/nexus/api/routes/chat_sessions.py](file://backend_design/nexus/api/routes/chat_sessions.py)
- [backend_design/nexus/api/routes/chat.py](file://backend_design/nexus/api/routes/chat.py)
- [backend_design/nexus/models/schemas.py](file://backend_design/nexus/models/schemas.py)

### 座舱控制（REST）
- 设备状态查询：获取座舱各子系统状态
- 指令下发：控制空调、座椅、车窗、媒体等
- 批量操作：支持一次性下发多条指令

请求示例要点
- 状态查询：GET /api/v1/cockpit/status
- 控制指令：POST /api/v1/cockpit/control {device, action, params}

响应示例要点
- 状态对象包含各子系统键值对
- 控制响应包含任务id与执行结果

**更新** 所有API端点现在通过网关端口8080访问

**章节来源**
- [backend_design/nexus/api/routes/cockpit.py](file://backend_design/nexus/api/routes/cockpit.py)
- [backend_design/nexus/models/schemas.py](file://backend_design/nexus/models/schemas.py)

### 数据平台（REST）
- 数据集管理：上传、下载、元数据更新
- 任务调度：触发数据处理任务，查询任务状态
- 指标与报表：导出统计结果

请求示例要点
- 上传数据：POST /api/v1/dataplatform/datasets/upload {file, metadata}
- 启动任务：POST /api/v1/dataplatform/tasks/run {type, params}

响应示例要点
- 上传响应包含文件id与存储位置
- 任务响应包含任务id与预计完成时间

**更新** 所有API端点现在通过网关端口8080访问

**章节来源**
- [backend_design/nexus/api/routes/dataplatform.py](file://backend_design/nexus/api/routes/dataplatform.py)
- [backend_design/nexus/models/schemas.py](file://backend_design/nexus/models/schemas.py)

### 健康检查与中间件状态（REST）
- 健康检查：GET /api/v1/health 返回服务可用性
- 中间件状态：GET /api/v1/middleware/status 返回缓存、队列等中间件运行状况

响应示例要点
- 健康检查返回status与timestamp
- 中间件状态返回各组件状态与延迟指标

**更新** 所有API端点现在通过网关端口8080访问

**章节来源**
- [backend_design/nexus/api/routes/health.py](file://backend_design/nexus/api/routes/health.py)
- [backend_design/nexus/api/routes/middleware_status.py](file://backend_design/nexus/api/routes/middleware_status.py)

### 设置管理（REST）
- 用户偏好：读取与更新个性化配置
- 系统设置：管理员可修改全局参数

请求示例要点
- 获取设置：GET /api/v1/settings/{scope}/{key}
- 更新设置：PUT /api/v1/settings/{scope}/{key} {value}

响应示例要点
- 设置对象包含scope、key、value与更新时间

**更新** 所有API端点现在通过网关端口8080访问

**章节来源**
- [backend_design/nexus/api/routes/settings.py](file://backend_design/nexus/api/routes/settings.py)
- [backend_design/nexus/models/schemas.py](file://backend_design/nexus/models/schemas.py)

### 车辆接口（REST）
- 车辆状态：查询电量、里程、胎压等
- 远程控制：解锁、锁车、开启空调等
- 事件订阅：通过WebSocket获取车辆实时事件

请求示例要点
- 车辆状态：GET /api/v1/vehicle/status
- 远程控制：POST /api/v1/vehicle/control {action, params}

响应示例要点
- 状态对象包含各项传感器与执行器读数
- 控制响应包含任务id与执行结果

**更新** 所有API端点现在通过网关端口8080访问

**章节来源**
- [backend_design/nexus/api/routes/vehicle.py](file://backend_design/nexus/api/routes/vehicle.py)
- [backend_design/nexus/models/schemas.py](file://backend_design/nexus/models/schemas.py)

### WebSocket实时通信
- 连接建立：客户端通过ws/wss协议连接到网关端口8080，网关转发至后端WebSocket处理器
- 消息格式：采用JSON封装，包含type、payload、trace_id等字段
- 事件类型：如message、status_update、task_progress、error等
- 状态管理：连接生命周期包括connected、subscribed、disconnected，支持重连与心跳
- **更新** 新增CORS白名单验证，仅允许配置的域名建立WebSocket连接

连接序列
```mermaid
sequenceDiagram
participant C as "客户端"
participant G as "NexusGate(端口8080)"
participant H as "Hub(WS)"
C->>G : "WS握手(携带JWT)"
G->>G : "CORS白名单验证"
G->>H : "转发握手"
H-->>C : "握手成功"
C->>H : "订阅事件{event_types}"
H-->>C : "推送事件{type,payload,trace_id}"
```

**图表来源**
- [backend_design/nexus/api/websocket.py](file://backend_design/nexus/api/websocket.py)
- [backend_design/nexus_gate/internal/ws/hub.go](file://backend_design/nexus_gate/internal/ws/hub.go)

**更新** WebSocket连接现在需要通过网关端口8080建立，并且会进行CORS白名单验证。

**章节来源**
- [backend_design/nexus/api/websocket.py](file://backend_design/nexus/api/websocket.py)
- [backend_design/nexus_gate/internal/ws/hub.go](file://backend_design/nexus_gate/internal/ws/hub.go)

### gRPC内部服务契约
- 服务定义：nexus.proto描述内部服务方法与消息类型
- 消息格式：统一的请求/响应结构，包含id、timestamp、payload等字段
- 服务契约：明确方法签名、错误码与重试策略

**章节来源**
- [backend_design/nexus_gate/proto/nexus.proto](file://backend_design/nexus_gate/proto/nexus.proto)

## 依赖关系分析
- 路由层依赖核心鉴权与数据模型
- 网关层依赖鉴权、限流与WebSocket Hub
- 数据模型集中定义于schemas，确保前后端一致性
- **更新** 网关层现在包含JWT令牌验证和CORS白名单验证逻辑

```mermaid
graph LR
AuthRoute["认证路由"] --> CoreAuth["核心鉴权"]
ChatRoute["聊天路由"] --> Schemas["数据模型"]
CockpitRoute["座舱路由"] --> Schemas
VehicleRoute["车辆路由"] --> Schemas
WSHandler["WebSocket处理器"] --> Hub["Hub(WS)"]
Gateway["网关(端口8080)"] --> Auth["鉴权/限流/CORS验证"]
Gateway --> Proxy["代理"]
Proxy --> App["FastAPI应用"]
```

**图表来源**
- [backend_design/nexus/api/routes/auth.py](file://backend_design/nexus/api/routes/auth.py)
- [backend_design/nexus/api/routes/chat.py](file://backend_design/nexus/api/routes/chat.py)
- [backend_design/nexus/api/routes/cockpit.py](file://backend_design/nexus/api/routes/cockpit.py)
- [backend_design/nexus/api/routes/vehicle.py](file://backend_design/nexus/api/routes/vehicle.py)
- [backend_design/nexus/api/websocket.py](file://backend_design/nexus/api/websocket.py)
- [backend_design/nexus/core/auth.py](file://backend_design/nexus/core/auth.py)
- [backend_design/nexus/models/schemas.py](file://backend_design/nexus/models/schemas.py)
- [backend_design/nexus_gate/internal/handlers/handlers.go](file://backend_design/nexus_gate/internal/handlers/handlers.go)
- [backend_design/nexus_gate/internal/ws/hub.go](file://backend_design/nexus_gate/internal/ws/hub.go)

**章节来源**
- [backend_design/nexus/api/routes/auth.py](file://backend_design/nexus/api/routes/auth.py)
- [backend_design/nexus/api/routes/chat.py](file://backend_design/nexus/api/routes/chat.py)
- [backend_design/nexus/api/routes/cockpit.py](file://backend_design/nexus/api/routes/cockpit.py)
- [backend_design/nexus/api/routes/vehicle.py](file://backend_design/nexus/api/routes/vehicle.py)
- [backend_design/nexus/api/websocket.py](file://backend_design/nexus/api/websocket.py)
- [backend_design/nexus/core/auth.py](file://backend_design/nexus/core/auth.py)
- [backend_design/nexus/models/schemas.py](file://backend_design/nexus/models/schemas.py)
- [backend_design/nexus_gate/internal/handlers/handlers.go](file://backend_design/nexus_gate/internal/handlers/handlers.go)
- [backend_design/nexus_gate/internal/ws/hub.go](file://backend_design/nexus_gate/internal/ws/hub.go)

## 性能考虑
- 网关层限流：对高频接口实施令牌桶或滑动窗口限流，避免雪崩
- 连接复用：WebSocket长连接减少握手开销，合理设置心跳间隔
- 数据模型校验：集中校验提升错误定位效率，减少无效请求进入业务层
- 异步处理：对耗时任务采用任务队列与回调机制，提高吞吐
- **更新** JWT令牌验证在网关层直接进行，减少了后端负载和网络往返

## 故障排查指南
- 统一异常类型：核心异常模块定义标准错误码与消息，便于前端展示与日志追踪
- 常见错误码
  - 401：未认证或令牌过期
  - 403：权限不足
  - 400：请求参数校验失败
  - 429：请求频率超限
  - 500：服务器内部错误
- 排查步骤
  - 检查Authorization头是否携带有效JWT
  - 查看网关限流日志与后端异常日志
  - 确认WebSocket事件订阅是否正确，trace_id是否一致
  - **更新** 确认客户端是否通过正确的网关端口8080访问
  - **更新** 检查CORS白名单配置是否包含当前域名

**更新** 新增网关相关的故障排查项，包括端口配置和CORS设置。

**章节来源**
- [backend_design/nexus/core/exceptions.py](file://backend_design/nexus/core/exceptions.py)

## 结论
NexusCockpit通过网关与后端解耦的架构，提供了完善的REST与WebSocket接口，配合JWT鉴权与统一异常处理，具备良好的可扩展性与可观测性。**更新** 新的统一网关架构进一步提升了系统的安全性和性能，所有外部访问现在都通过端口8080进行统一管理。建议在客户端实现中遵循版本化策略、幂等设计与错误重试机制，以提升稳定性与用户体验。

## 附录

### API版本管理与向后兼容
- 版本前缀：所有REST端点使用/api/v1前缀，便于未来演进
- 兼容性策略
  - 新增字段：保持向后兼容，旧客户端忽略未知字段
  - 废弃字段：保留至少两个大版本，提供迁移提示
  - 破坏性变更：通过新版本前缀发布，并提供迁移指南
- **更新** 端口变更：从直接访问后端端口改为通过网关端口8080访问

### SDK集成指南与最佳实践
- 初始化SDK：配置网关地址（端口8080）、超时与重试策略
- 认证流程：登录后缓存JWT，自动刷新过期令牌
- 错误处理：捕获统一错误码，展示友好提示
- WebSocket集成：实现重连与心跳检测，订阅必要事件
- 幂等设计：对写操作生成唯一请求id，避免重复提交
- **更新** 所有API调用现在必须通过网关端口8080进行

**更新** SDK集成指南已更新以反映新的网关架构和端口要求。

### 网关配置示例
**新增** 网关主要配置项：

```yaml
gateway:
  port: 8080
  cors_whitelist:
    - http://localhost:3000
    - https://your-domain.com
  jwt_secret: "your-secret-key"
  rate_limit:
    requests_per_minute: 60
    burst_size: 10
  backend_url: "http://localhost:8000"
```

**章节来源**
- [backend_design/nexus_gate/internal/config/config.go](file://backend_design/nexus_gate/internal/config/config.go)