# NexusCockpit CAN 接口协议文档

> 版本: 2.2.0 | 更新日期: 2026-08-01

---

## 目录

1. [协议概述](#1-协议概述)
2. [车控适配架构](#2-车控适配架构)
3. [HTTP 接口协议定义](#3-http-接口协议定义)
4. [车辆状态查询协议](#4-车辆状态查询协议)
5. [错误码定义](#5-错误码定义)
6. [WebSocket 实时通信协议](#6-websocket-实时通信协议)
7. [安全与鉴权](#7-安全与鉴权)
8. [常见对接问题排查](#8-常见对接问题排查)

---

## 1. 协议概述

NexusCockpit 车控系统通过 **适配器模式** 对接车机硬件，支持三种适配模式：

| 模式 | 通信协议 | 适用场景 |
|------|----------|----------|
| Mock | 进程内调用 | 开发调试、交付验收（无车机环境） |
| HTTP | RESTful HTTP/JSON | 对接 T-Box、车控网关 |
| MCP | stdio JSON-RPC | 对接 MCP 协议设备 |

**默认配置**: `VEHICLE_ADAPTER=mock`（交付验收时使用模拟模式，不发送真实指令）

---

## 2. 车控适配架构

```
用户语音/文本指令
    ↓
Agent 意图路由 → 车控专家 (Vehicle Expert)
    ↓
技能调用 (Skills: climate/windows/doors/seats/navigation/media)
    ↓
VehicleAdapter (Mock / HTTP / MCP)
    ↓
车控网关 / T-Box / CAN 总线
```

### 适配器切换

```bash
# .env 配置
VEHICLE_ADAPTER=mock     # 模拟模式（默认）
VEHICLE_ADAPTER=http     # HTTP 对接模式
VEHICLE_ADAPTER=mcp      # MCP 协议模式
```

---

## 3. HTTP 接口协议定义

### 3.1 通用约定

| 项目 | 值 |
|------|-----|
| 协议 | HTTP/1.1 |
| 数据格式 | JSON (UTF-8) |
| 认证 | Bearer Token（可选） |
| 超时 | 10 秒（可配置 `VEHICLE_API_TIMEOUT`） |
| Base URL | 通过 `VEHICLE_API_BASE_URL` 配置 |

### 3.2 空调控制接口

**请求**: `POST /api/v1/climate`

```json
{
  "op": "set_temp",
  "target_temp": 24,
  "fan_speed": 3,
  "mode": "auto",
  "area": "all"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `op` | string | 是 | 操作类型: `set_temp`/`temp_up`/`temp_down`/`set_fan`/`set_mode`/`turn_on`/`turn_off` |
| `target_temp` | int | 否 | 目标温度 (16-30℃)，`set_temp` 时必填 |
| `fan_speed` | int | 否 | 风量等级 (0-7)，`set_fan` 时必填 |
| `mode` | string | 否 | 模式: `auto`/`cool`/`heat`/`fan`/`defrost` |
| `area` | string | 否 | 区域: `all`/`driver`/`passenger`/`rear` |

**响应**:

```json
{
  "success": true,
  "result": {
    "current_temp": 24,
    "fan_speed": 3,
    "mode": "auto",
    "area": "all"
  },
  "message": "空调温度已设置为24度"
}
```

### 3.3 车窗控制接口

**请求**: `POST /api/v1/windows`

```json
{
  "op": "open",
  "position": "all",
  "level": 100
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `op` | string | 是 | `open`/`close`/`set_position` |
| `position` | string | 是 | `all`/`front_left`/`front_right`/`rear_left`/`rear_right`/`sunroof` |
| `level` | int | 否 | 开度百分比 (0-100)，`set_position` 时必填 |

### 3.4 车门控制接口

**请求**: `POST /api/v1/doors`

```json
{
  "op": "lock",
  "position": "all"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `op` | string | 是 | `lock`/`unlock`/`open`/`close` |
| `position` | string | 是 | `all`/`front_left`/`front_right`/`rear_left`/`rear_right`/`trunk` |

### 3.5 座椅控制接口

**请求**: `POST /api/v1/seats`

```json
{
  "op": "heat_on",
  "position": "driver",
  "level": 2
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `op` | string | 是 | `heat_on`/`heat_off`/`vent_on`/`vent_off`/`set_position` |
| `position` | string | 是 | `driver`/`passenger`/`rear_left`/`rear_right` |
| `level` | int | 否 | 加热等级 (1-3) 或位置百分比 (0-100) |

### 3.6 导航控制接口

**请求**: `POST /api/v1/navigation`

```json
{
  "op": "set_destination",
  "destination": "上海虹桥火车站",
  "lat": 31.1942,
  "lng": 121.3194
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `op` | string | 是 | `set_destination`/`cancel`/`start`/`pause` |
| `destination` | string | 否 | 目的地名称，`set_destination` 时必填 |
| `lat` | float | 否 | 纬度（可选，精确导航时使用） |
| `lng` | float | 否 | 经度（可选，精确导航时使用） |

### 3.7 媒体控制接口

**请求**: `POST /api/v1/media`

```json
{
  "op": "play",
  "source": "local",
  "track_id": "track_001"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `op` | string | 是 | `play`/`pause`/`next`/`prev`/`set_volume` |
| `source` | string | 否 | 音源: `local`/`bluetooth`/`online` |
| `track_id` | string | 否 | 曲目 ID |
| `volume` | int | 否 | 音量 (0-100)，`set_volume` 时必填 |

---

## 4. 车辆状态查询协议

**请求**: `GET /api/v1/status`

**响应**:

```json
{
  "success": true,
  "result": {
    "climate": {
      "current_temp": 24,
      "fan_speed": 3,
      "mode": "auto",
      "ac_on": true
    },
    "windows": {
      "front_left": 0,
      "front_right": 0,
      "rear_left": 0,
      "rear_right": 0,
      "sunroof": 0
    },
    "doors": {
      "front_left": "closed",
      "front_right": "closed",
      "rear_left": "closed",
      "rear_right": "closed",
      "trunk": "closed",
      "locked": true
    },
    "seats": {
      "driver": { "heat_level": 0, "vent_on": false },
      "passenger": { "heat_level": 0, "vent_on": false }
    },
    "media": {
      "playing": false,
      "source": "local",
      "volume": 50,
      "track_name": ""
    },
    "navigation": {
      "active": false,
      "destination": ""
    },
    "vehicle": {
      "speed": 0,
      "odometer": 12345,
      "tire_pressure": {
        "front_left": 2.5,
        "front_right": 2.5,
        "rear_left": 2.4,
        "rear_right": 2.4
      },
      "fuel_level": 75
    }
  }
}
```

---

## 5. 错误码定义

| 错误码 | HTTP 状态码 | 说明 | 处理建议 |
|--------|------------|------|----------|
| `SUCCESS` | 200 | 操作成功 | — |
| `INVALID_PARAMS` | 400 | 参数错误 | 检查请求体字段 |
| `UNAUTHORIZED` | 401 | 未授权 | 检查 Token 是否有效 |
| `FORBIDDEN` | 403 | 权限不足 | 检查 RBAC 角色权限 |
| `DEVICE_OFFLINE` | 503 | 车机离线 | 检查车控网关连接 |
| `COMMAND_TIMEOUT` | 504 | 指令超时 | 检查车机响应时间 |
| `COMMAND_FAILED` | 500 | 指令执行失败 | 查看车控网关日志 |
| `VEHICLE_MOVING` | 409 | 行驶中禁止操作 | 停车后重试（部分指令） |

---

## 6. WebSocket 实时通信协议

### 6.1 连接地址

```
ws://<网关地址>:8080/cockpit/{cockpit_id}/ws/chat
```

### 6.2 消息格式

**客户端 → 服务端**:

```json
{ "type": "text", "data": "把空调调到24度" }
{ "type": "audio", "data": "<base64_wav_16khz_mono>" }
```

**服务端 → 客户端**:

```json
{ "type": "thinking", "data": { "message": "正在思考..." } }
{ "type": "intent", "data": { "intent": "vehicle_control", "source": "heuristic" } }
{ "type": "action", "data": { "action": "vehicle_climate_set_temp" } }
{ "type": "chunk", "data": { "chunk": "好的" } }
{ "type": "chunk", "data": { "chunk": "已为您设置到24度" } }
{ "type": "done", "data": { "response": "好的，已为您设置到24度", "latency_ms": 800 } }
{ "type": "audio", "data": "<base64_wav_22050hz>" }
{ "type": "error", "data": { "code": "COMMAND_TIMEOUT", "message": "车控指令超时" } }
```

---

## 7. 安全与鉴权

### 7.1 JWT 认证

所有车控请求需携带 JWT Token：

```
Authorization: Bearer <your_jwt_token>
```

Token 通过 Go 网关 `/auth/login` 接口获取。

### 7.2 RBAC 权限控制

| 角色 | 车控权限 | 说明 |
|------|----------|------|
| `admin` | 全部 | 管理员可执行所有车控指令 |
| `cockpit_user` | 全部 | 普通座舱用户可执行车控指令 |
| `guest` | 仅查询 | 仅可查询车辆状态，不可执行控制指令 |

### 7.3 行车安全限制

以下指令在车辆行驶中（速度 > 0）将被拒绝：

| 指令 | 限制条件 |
|------|----------|
| 车门打开 | 速度 > 0 时拒绝 |
| 车窗全开 | 速度 > 80 km/h 时拒绝 |
| 导航取消 | 速度 > 0 时需二次确认 |

---

## 8. 常见对接问题排查

### Q: 车控指令无响应

```bash
# 1. 检查适配器模式
echo $VEHICLE_ADAPTER
# 应为 http 或 mcp（非 mock）

# 2. 检查车控网关连通性
curl -X GET http://<车控网关IP>:<端口>/api/v1/status

# 3. 查看后端日志
docker compose logs nexus_ai | grep -i "vehicle"
```

### Q: HTTP 对接返回 503 (DEVICE_OFFLINE)

```
原因: 车控网关无法连接到 CAN 总线
排查:
1. 检查 T-Box 电源和网络连接
2. 检查 CAN 总线物理连接
3. 查看车控网关日志
```

### Q: 车控指令执行但无效果

```
原因: 指令参数不匹配或车机不支持该功能
排查:
1. 确认车辆型号支持对应功能（如座椅通风）
2. 检查指令参数范围（如温度 16-30℃）
3. 查看车控网关返回的 result 字段
```

### Q: WebSocket 连接频繁断开

```bash
# 1. 检查网络稳定性
ping <网关地址>

# 2. 检查心跳配置
# SSE 心跳间隔通过 SSE_HEARTBEAT_INTERVAL 配置
# WebSocket 默认 30 秒心跳

# 3. 检查 Go 网关日志
docker compose logs nexus_gate | grep -i "ws"
```
