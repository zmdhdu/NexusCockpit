# L1 核心层 (Core)

> 对应代码: `nexus/config.py` + `nexus/core/`

## 职责

提供全项目共享的基础设施：
- **配置中心** — 统一管理所有环境变量和配置项
- **结构化日志** — 基于 structlog 的 JSON 日志
- **异常体系** — 统一的异常分类和处理
- **熔断器** — 保护云端 API 调用的稳定性
- **JWT 认证** — 令牌签发、验证、依赖注入
- **OSS 对象存储** — 阿里云 OSS 上传/下载/签名 URL

## 模块清单

### config.py — 配置中心

使用 Pydantic Settings 实现类型安全的配置管理。

```python
from nexus.config import get_config

config = get_config()
config.llm.ark_api_key      # LLM API Key
config.milvus.uri           # Milvus 连接 URI
config.redis.url             # Redis 连接 URL
config.asr.funasr_model_path # ASR 模型路径 (相对路径)
config.asr.resolved_funasr_path()  # 解析为绝对路径
```

**配置子类**:

| 类名 | 说明 | 环境变量前缀 |
|------|------|-------------|
| `LLMConfig` | LLM 配置 | `ARK_*`, `LLM_*`, `EMBEDDING_*` |
| `MilvusConfig` | Milvus 配置 | `MILVUS_*` |
| `Neo4jConfig` | Neo4j 配置 | `NEO4J_*` |
| `RedisConfig` | Redis 配置 | `REDIS_*`, `SEMANTIC_CACHE_*` |
| `RabbitMQConfig` | RabbitMQ 配置 | `RABBITMQ_*` |
| `MySQLConfig` | MySQL 配置 | `MYSQL_*` |
| `JWTConfig` | JWT 配置 | `JWT_*` |
| `VehicleConfig` | 车控配置 | `VEHICLE_*` |
| `ASRConfig` | ASR/TTS/声纹配置 | `FUNASR_*`, `CAM_*`, `COSYVOICE_*` |
| `DataConfig` | 数据目录配置 | `FOOD_*`, `KNOWLEDGE_*`, `UPLOAD_*` |
| `LangfuseConfig` | 追踪配置 | `LANGFUSE_*` |
| `ServerConfig` | 服务器配置 | `HOST`, `PORT`, `DEBUG` |
| `TavilyConfig` | 搜索配置 | `TAVILY_*` |

### core/logger.py — 结构化日志

```python
from nexus.core.logger import get_logger, setup_logging

setup_logging()  # 应用启动时调用一次
logger = get_logger(__name__)
logger.info("message", user_id="123", action="chat")
```

### core/exceptions.py — 异常体系

```python
from nexus.core.exceptions import NexusError, LLMError, VectorStoreError

# 所有自定义异常都继承自 NexusError
# FastAPI 全局异常处理器会自动捕获并返回结构化错误响应
```

### core/circuit_breaker.py — 熔断器

```python
from nexus.core.circuit_breaker import CircuitBreaker

breaker = CircuitBreaker(name="llm_api", threshold=5, timeout=60)

@breaker.protect
async def call_llm(prompt: str) -> str:
    ...
```

### core/auth.py — JWT 认证

```python
from nexus.core.auth import create_access_token, get_current_user
from fastapi import Depends

# 签发令牌
token = create_access_token(data={"sub": "admin"})

# 在路由中强制认证
@router.post("/command")
async def command(user: str = Depends(get_current_user)):
    ...
```

- 基于 `python-jose` 实现 JWT 签发和验证
- `get_current_user` 作为 FastAPI 依赖注入，自动校验 Bearer Token
- 支持 `HTTPBearer` 自动提取 Authorization Header
- 未配置 JWT_SECRET 时，认证降级为直通（开发模式）

### core/oss.py — OSS 对象存储

```python
from nexus.core.oss import OSSStorage

oss = OSSStorage()
oss.connect()
url = oss.upload("file.txt", data=b"...")  # 上传并返回公开读 URL
oss.download("file.txt")                    # 下载文件内容
signed = oss.sign_url("file.txt", expires=3600)  # 生成签名 URL
```

- 阿里云 OSS 封装，支持上传/下载/签名 URL
- 自动从 config 读取 OSS 配置（bucket/endpoint/access_key）

## 设计原则

1. **无业务逻辑** — 核心层只提供工具，不包含任何业务逻辑
2. **零依赖** — 核心层不依赖项目中其他任何层
3. **全局单例** — 配置通过 `lru_cache` 实现单例，避免重复加载
4. **路径解析** — 所有文件路径使用相对路径配置，通过 `resolved_*()` 方法获取绝对路径
