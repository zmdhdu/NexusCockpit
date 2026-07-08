# L5 中间件层 (Middleware)

> 对应代码: `nexus/middleware/`

## 职责

提供横切关注点的基础设施：
- **语义缓存** — Redis 向量搜索实现语义级缓存（含副作用隔离）
- **限流器** — Redis Lua 脚本原子化滑动窗口限流
- **任务队列** — Celery + RabbitMQ 异步任务
- **会话存储** — Redis 持久化会话历史（降级内存回退）

## 语义缓存 (redis_cache.py) — v2.0 Redis Stack KNN

v2.0 从 O(n) 遍历升级为 RediSearch VECTOR KNN 向量检索 O(log n)。

```python
from nexus.middleware.redis_cache import SemanticCache

cache = SemanticCache(embedding_service)
await cache.connect()

# 查询缓存 (KNN 向量检索)
hit = await cache.get(query="把空调调到24度", user_id="u1")
if hit:
    return hit["response"]  # 缓存命中

# 写入缓存 — 有副作用的响应（如车控指令）禁止缓存
await cache.set(
    query="把空调调到24度",
    response={"response": "好的，已为您将空调调到24度"},
    user_id="u1",
    ttl=3600,                # v2.0: TTL 分级（闲聊 1h、知识库 24h）
    has_side_effect=False,   # 车控指令必须设为 True，防止缓存命中后不执行
)
```

### 工作原理 (v2.0 KNN)

```
用户查询
  → Embedding 向量化
  → RediSearch FT.SEARCH KNN (相似度 > 0.92)
    ├─ 命中 → 返回缓存的响应
    └─ 未命中 → 走正常流程 → 结果写入缓存

Fallback: RediSearch 不可用时自动回退到 O(n) 遍历模式
```

### v2.0 新增特性

- **KNN 向量检索**: RediSearch VECTOR FLAT 索引，O(log n) 复杂度
- **按用户分片**: `user_id` TAG 字段隔离
- **TTL 分级**: 闲聊 1h、知识库 24h、车控永不上缓存
- **副作用隔离**: `has_side_effect=True` 的响应永不写入缓存
- **降级模式**: Redis Stack 不可用时自动回退到 O(n) 遍历

### 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SEMANTIC_CACHE_ENABLED` | `true` | 是否启用 |
| `SEMANTIC_CACHE_SIMILARITY_THRESHOLD` | `0.92` | 相似度阈值 |
| `SEMANTIC_CACHE_TTL_SECONDS` | `3600` | 缓存过期时间 |

## 限流器 (rate_limiter.py)

```python
from nexus.middleware.rate_limiter import RateLimiter

limiter = RateLimiter()
await limiter.connect()

# 检查是否允许
allowed = await limiter.check(user_id="u1", limit=60, window=60)
if not allowed:
    raise RateLimitError("请求过于频繁")
```

### 工作原理

- 基于 Redis Lua 脚本的**原子化**滑动窗口算法
- Lua 脚本确保 ZADD + ZCARD + ZREMRANGEBYSCORE 在单次 Redis 调用中原子执行
- 避免非原子操作导致的超限请求污染计数问题
- 每个 `user_id` 独立计数
- 超出限制返回 `False`

## 会话存储 (session_store.py)

```python
from nexus.middleware.session_store import SessionStore

store = SessionStore()
await store.connect()

# 读取会话历史
history = await store.async_get("user_123")

# 写入会话历史
await store.async_set("user_123", [
    {"role": "user", "content": "打开空调"},
    {"role": "assistant", "content": "已为您打开空调"},
])
```

### 工作原理

- Redis 持久化存储会话历史，支持多实例部署
- Redis 不可用时自动降级为内存 dict 存储
- 每个会话以 `session:{user_id}` 为 key 存储在 Redis
- `async_close()` 在应用关闭时清理连接

## 任务队列 (task_queue.py)

```python
from nexus.middleware.task_queue import celery_app, submit_task

# 提交异步任务
task = submit_task("nexus.tasks.memory_store", args=(user_id, content))
```

### Celery 配置

```python
celery_app = Celery(
    "nexus",
    broker=RabbitMQ_URL,      # amqp://guest:guest@localhost:5672//
    backend=REDIS_URL,         # redis://localhost:6379/1
)
```

## 熔断器 (core/circuit_breaker.py)

虽然代码位于 `core/` 层，但通常在中间件层使用：

```python
from nexus.core.circuit_breaker import CircuitBreaker

llm_breaker = CircuitBreaker(
    name="llm_api",
    threshold=5,       # 连续失败 5 次后熔断
    timeout=60,        # 60 秒后尝试恢复
)

@llm_breaker.protect
async def call_llm(prompt):
    return await llm_client.chat.completions.create(...)
```

### 状态机

```
CLOSED → (失败次数 >= threshold) → OPEN
   ↑                                   │
   │                              (等待 timeout)
   │                                   │
   └─── (半开探测成功) ← HALF_OPEN ←───┘
```

## 设计原则

1. **非侵入** — 中间件通过装饰器或显式调用，不侵入业务代码
2. **可降级** — Redis 不可用时，缓存/限流自动降级为直通
3. **可配置** — 所有参数通过环境变量配置
4. **可观测** — 缓存命中率、限流次数等指标暴露给 Prometheus
