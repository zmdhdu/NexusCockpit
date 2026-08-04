---
kind: configuration_system
name: NexusCockpit 配置系统 — Pydantic Settings 分层配置与 .env 覆盖机制
category: configuration_system
scope:
    - '**'
source_files:
    - backend_design/nexus/config/__init__.py
    - backend_design/nexus/config/_common.py
    - backend_design/nexus/config/llm.py
    - backend_design/nexus/config/database.py
    - backend_design/nexus/config/cache.py
    - backend_design/nexus/config/vehicle.py
    - backend_design/nexus/config/asr.py
    - backend_design/nexus/config/observability.py
    - backend_design/nexus/config/server.py
    - backend_design/nexus/config/providers.py
    - backend_design/nexus/config/data.py
    - backend_design/nexus/config/cockpit.py
    - .env
    - frontend_design/.env.local.example
    - docker-compose.yml
---

## 1. 系统概览

NexusCockpit 使用 **Pydantic v2 + pydantic-settings** 构建分层配置系统，通过 `nexus.config` 包将全局配置拆分为 11 个按子系统划分的模块（LLM、数据库、缓存、车控、ASR、可观测性、服务器、认证、第三方服务、数据目录、多座舱），由 `AppConfig` 聚合为单一入口。配置加载遵循 `.env.local` > `.env` > 环境变量 > 默认值 的优先级策略，并通过 `validation_alias` 将大写环境变量映射到小写字段。

## 2. 核心架构与约定

### 2.1 配置类分层
- `_common.py`：定义项目根路径自动定位、`.env` 文件加载策略（优先 `.env.local`，不存在则回退 `.env`）、`_resolve_path()` 相对路径解析工具。
- `__init__.py`：`AppConfig(BaseSettings)` 聚合所有子配置，提供 `get_config()` 全局单例（`lru_cache(maxsize=1)`）和快捷访问函数 `get_llm_config()`、`get_milvus_config()`、`get_redis_config()`。
- 各子系统配置文件（`llm.py`、`database.py`、`cache.py`、`vehicle.py`、`asr.py`、`observability.py`、`server.py`、`providers.py`、`data.py`、`cockpit.py`）各自继承 `BaseSettings`，通过 `model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")` 绑定环境文件。

### 2.2 环境变量命名约定
每个字段通过 `Field(..., validation_alias="UPPER_CASE_VAR")` 声明对应的大写环境变量名，例如：
- `ServerConfig.host` ← `HOST`
- `LLMConfig.provider` ← `LLM_PROVIDER`
- `MilvusConfig.uri` ← `MILVUS_URI`
- `RedisConfig.password` ← `REDIS_PASSWORD`

### 2.3 路径解析策略
- 所有模型/数据路径统一以 `./` 开头的相对路径形式配置（如 `./models/asr/sensevoice`、`./data/food`）。
- `ASRConfig.model_post_init` 和 `DataConfig.resolved_*` 方法在初始化时将相对路径通过 `_resolve_path()` 解析为基于项目根目录的绝对路径，确保从任意工作目录启动时路径正确。

### 2.4 计算字段与派生配置
多个配置类使用 `@computed_field` 或 `@property` 生成派生值：
- `MySQLConfig.url` → `mysql+aiomysql://user:pass@host:port/db?charset=utf8mb4`
- `RedisConfig.url` → `redis://[:password@]host:port/db`
- `LLMConfig.embedding_url` → `{base_url}/embeddings`
- `LLMConfig.is_local` → 根据 `provider == "local"` 判断本地模式
- `ServerConfig.cors_origins_list` → 逗号分隔字符串转列表

### 2.5 LLM 提供商切换逻辑
`LLMConfig.model_post_init` 实现一键切换：当 `LLM_PROVIDER=local` 时，自动将 `ark_base_url`、`ark_api_key`、`llm_model`、`timeout` 切换到 `fallback_*` 对应的本地 llama.cpp 参数，无需手动修改多处配置。

## 3. 关键文件与职责

| 文件 | 职责 |
|------|------|
| `backend_design/nexus/config/__init__.py` | 全局 `AppConfig` 聚合、单例工厂、导出接口 |
| `backend_design/nexus/config/_common.py` | 项目根路径定位、`.env` 加载策略、`_resolve_path()` |
| `backend_design/nexus/config/llm.py` | LLM 连接参数、云端/本地切换、降级通知开关 |
| `backend_design/nexus/config/database.py` | Milvus/Neo4j/MySQL 连接参数、URL 生成 |
| `backend_design/nexus/config/cache.py` | Redis 连接、语义缓存阈值/TTL |
| `backend_design/nexus/config/vehicle.py` | 车控适配器（mock/http/mcp）及 MCP 启动参数 |
| `backend_design/nexus/config/asr.py` | ASR/TTS/声纹模型路径、说话人注册目录 |
| `backend_design/nexus/config/observability.py` | Langfuse 追踪、Prometheus/Grafana 地址 |
| `backend_design/nexus/config/server.py` | FastAPI 监听、CORS、JWT/RBAC 认证参数 |
| `backend_design/nexus/config/providers.py` | 部署模式开关（vector_store/graph_store/cache/reranker/checkpoint） |
| `backend_design/nexus/config/data.py` | 数据目录路径、记忆压缩/摘要参数 |
| `backend_design/nexus/config/cockpit.py` | 多座舱数量、Go 网关、Tavily/高德/和风天气 API 密钥 |
| `.env` | 统一默认配置（提交 Git，开箱即用） |
| `.env.local` | 本机覆盖配置（不提交，含个人密钥） |
| `frontend_design/.env.local.example` | 前端 Next.js 环境变量模板 |
| `docker-compose.yml` | 容器化中间件配置，通过 `environment` 注入服务间通信地址 |

## 4. 约束与规则

- **环境变量优先级**：运行时环境变量 > `.env.local` > `.env` > 字段默认值（由 `dotenv.load_dotenv(override=True)` 保证）。
- **路径规范**：所有文件路径必须使用 `./` 前缀的相对路径，禁止硬编码绝对路径，由 `_resolve_path()` 统一解析。
- **敏感信息隔离**：API Key、密码等敏感字段必须放在 `.env.local`，`.env` 仅包含开发默认值。
- **Provider 固定化**：部署模式（`ProvidersConfig`）当前固定为 `local`，保留配置项仅为后续灵活切换预留。
- **Docker 环境变量覆盖**：`docker-compose.yml` 中通过 `environment` 覆盖容器内服务地址（如 `MILVUS_HOST=milvus`），宿主机端口避让 Windows Hyper-V 保留范围（如 Redis 16379→6379、Neo4j 17687→7687）。
- **前端-后端密码一致性**：`NEXT_PUBLIC_DEFAULT_PASSWORD` 必须与后端 `.env` 中 `RBAC_USER_PASSWORD` 保持一致，否则自动登录返回 401。

## 5. 扩展新配置项的步骤

1. 在对应子系统文件中新增 `Field(default=..., validation_alias="VAR_NAME")` 字段。
2. 在 `AppConfig` 中添加该子配置实例（如 `my_feature: MyFeatureConfig = Field(default_factory=MyFeatureConfig)`）。
3. 在 `.env` 中添加默认值，如需覆盖则在 `.env.local` 中设置。
4. 如需路径解析，在 `model_post_init` 中调用 `_resolve_path()`。
5. 可选：添加 `@computed_field` 生成派生 URL/布尔值。
