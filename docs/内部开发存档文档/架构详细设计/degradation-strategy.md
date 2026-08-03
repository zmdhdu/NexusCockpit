# 全局降级策略

> NexusCockpit 各模块的降级策略设计

## 降级原则

1. **不崩溃**: 任何依赖服务不可用时，系统应继续运行（降级模式）
2. **用户感知**: 降级时通知用户（可配置 `DEGRADATION_NOTIFY_USER`）
3. **数据安全**: 降级不导致数据丢失或错误数据
4. **可恢复**: 依赖恢复后自动回到正常模式

## 各模块降级策略

### LLM 服务

| 层级 | 触发条件 | 降级动作 |
|------|---------|---------|
| 正常 | 云端 LLM 可用 | 使用 DeepSeek-V3（硅基流动） |
| L1 降级 | 云端 API 超时/限流 | 降级到本地 Qwen3.5-4B（llama.cpp） |
| L2 降级 | 本地 LLM 也不可用 | 返回预设错误消息 |

**配置**:
```env
LLM_FALLBACK_ENABLED=true
LLM_FALLBACK_BASE_URL=http://127.0.0.1:8082/v1
LLM_FALLBACK_MODEL=qwen3.5-4b-local
```

**代码位置**: `backend_design/nexus/agent/responder.py`

### 声纹识别

| 层级 | 触发条件 | 降级动作 |
|------|---------|---------|
| 正常 | CAM++ 模型已加载 | 提取声纹 embedding，匹配用户 |
| L1 降级 | 模型未加载 | 返回 None，跳过声纹验证 |
| L2 降级 | 无注册用户 | 返回未验证状态，使用默认偏好 |

**v2.2 修复**: 不再返回假随机向量，避免"假装验证成功"的安全风险。

**代码位置**: `backend_design/nexus/core/voiceprint.py`

### 向量检索 (Milvus)

| 层级 | 触发条件 | 降级动作 |
|------|---------|---------|
| 正常 | Milvus 连接正常 | KNN 向量检索 |
| L1 降级 | Milvus 连接失败 | 跳过向量检索，仅用图谱 + BM25 |
| L2 降级 | 三路都失败 | 返回空结果，LLM 纯靠上下文回答 |

### 图谱检索 (Neo4j)

| 层级 | 触发条件 | 降级动作 |
|------|---------|---------|
| 正常 | Neo4j 连接正常 | Cypher 关系遍历 |
| L1 降级 | Neo4j 连接失败 | 跳过图谱检索，仅用向量 + BM25 |

### 语义缓存 (Redis)

| 层级 | 触发条件 | 降级动作 |
|------|---------|---------|
| 正常 | Redis + RediSearch | KNN 向量缓存检索 |
| L1 降级 | RediSearch 不可用 | 降级为 O(n) scan 遍历 |
| L2 降级 | Redis 不可用 | 跳过缓存，每次走 LLM |

### 车控适配器

| 层级 | 触发条件 | 降级动作 |
|------|---------|---------|
| 正常 | VEHICLE_ADAPTER=http | 真实车控指令 |
| L1 降级 | HTTP 超时 | 返回错误，不影响对话 |
| mock 模式 | VEHICLE_ADAPTER=mock | 返回模拟数据（开发测试用） |

### 定位服务

| 层级 | 触发条件 | 降级动作 |
|------|---------|---------|
| 正常 | GPS + 高德 API | 精确逆地理编码 |
| L1 降级 | 高德 API 不可用 | 降级到 Nominatim |
| L2 降级 | GPS 不可用 | 降级到 IP 定位 |

## 降级通知

```env
DEGRADATION_NOTIFY_USER=true   # 通知用户（如"语音服务暂时不可用"）
DEGRADATION_NOTIFY_ADMIN=true  # 通知管理员（记入日志 + 告警）
```
