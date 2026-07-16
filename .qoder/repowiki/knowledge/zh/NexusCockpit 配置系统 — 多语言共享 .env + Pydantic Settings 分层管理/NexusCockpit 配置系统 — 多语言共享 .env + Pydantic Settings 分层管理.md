---
kind: configuration_system
name: NexusCockpit 配置系统 — 多语言共享 .env + Pydantic Settings 分层管理
category: configuration_system
scope:
    - '**'
source_files:
    - backend_design/nexus/config.py
    - backend_design/nexus_gate/internal/config/config.go
    - .env.example
    - docker-compose.yml
    - frontend_design/.env.local.example
---

## 1. 系统概览

NexusCockpit 采用**单一 `.env` 文件 + 多语言类型安全加载器**的配置体系：项目根目录的 `.env`（或按 `APP_ENV` 切换的 `.env.local` / `.env.prod`）是唯一的配置来源，Python 后端通过 `pydantic-settings` 强类型解析，Go 网关直接读取同名环境变量，前端 Next.js 使用独立的 `.env.local`。

## 2. 核心组件与职责

- **Python 配置中心** `backend_design/nexus/config.py`
  - 定义 `AppConfig` 聚合类，内含 `LLMConfig`、`MilvusConfig`、`Neo4jConfig`、`RedisConfig`、`MySQLConfig`、`JWTConfig`、`VehicleConfig`、`ASRConfig`、`OSSConfig`、`LangfuseConfig`、`ServerConfig`、`ProvidersConfig`、`CockpitSettings`、`ObservabilityConfig` 等子配置。
  - 每个子配置均为 `BaseSettings`，字段通过 `Field(validation_alias="ENV_KEY")` 映射到环境变量，并带默认值。
  - 提供 `get_config()` 单例（`lru_cache(maxsize=1)`），以及 `get_llm_config()` 等快捷函数。
  - 路径解析：`_resolve_path()` 将相对路径（如 `./models/asr/sensevoice`）基于项目根目录解析为绝对路径，避免工作目录差异导致的路径失效。
  - 生产环境安全检查：`model_post_init` 在 `APP_ENV=prod` 时检测弱密钥/默认密码并输出警告。

- **Go 网关配置** `backend_design/nexus_gate/internal/config/config.go`
  - 独立从 `os.Getenv` 读取 `NEXUS_GATE_*`、`JWT_SECRET`、`REDIS_*`、`RBAC_*`、`COCKPIT_*`、`VOICEPRINT_*` 等变量，复用同一份 `.env`。
  - 提供 `Load()` / `Get()` 全局访问，以及 `AIBaseURL()` 便捷方法。

- **环境变量模板** `.env.example`
  - 完整列出所有后端可配置项，含 LLM、向量库、图谱、缓存、消息队列、OSS、双模式 provider 开关、v2.1 多座舱参数、Go 网关参数等，作为开发者的配置清单。

- **Docker Compose 编排** `docker-compose.yml`
  - 通过 `env_file: .env` 注入配置，并在 `environment:` 中覆盖容器内服务发现地址（如 `REDIS_HOST=redis`、`MILVUS_URI=http://milvus:19530`）。
  - 挂载 `./models`、`./data`、`./assets` 使模型和数据持久化。

- **前端配置** `frontend_design/.env.local.example`
  - 仅包含 `NEXT_PUBLIC_API_URL` 和 `NEXT_PUBLIC_WS_URL`，由 Next.js 构建期注入，与后端配置解耦。

## 3. 架构与约定

| 维度 | 约定 |
|------|------|
| **配置文件优先级** | `APP_ENV=prod` → `.env.prod`；`APP_ENV=local` 或未设置 → `.env.local`；都不存在则回退 `.env`。通过 `dotenv.load_dotenv(override=True)` 显式加载，避免被其他 `.env` 干扰。 |
| **命名规范** | 环境变量统一大写蛇形（`ARK_API_KEY`、`MILVUS_HOST`、`VEHICLE_ADAPTER` 等），Python 侧用 `validation_alias` 映射，Go 侧直接 `os.Getenv`。 |
| **路径策略** | 所有本地路径以 `./` 开头（如 `./models/asr/sensevoice`），由 `_resolve_path()` 解析为项目根下的绝对路径，保证跨目录启动一致。 |
| **Provider 切换** | `ProvidersConfig` 暴露 `vector_store` / `graph_store` / `cache` / `reranker` 四个开关，取值 `local` / `cloud` / `none`，配合各组件配置实现一键切换本地 Docker 与云端托管。 |
| **单例模式** | Python 端 `get_config()` 使用 `@lru_cache` 保证进程内唯一实例；Go 端 `cfg` 包级变量懒加载。 |
| **安全校验** | 生产环境自动检测默认弱密钥、默认数据库密码、`CORS=*` 等不安全配置并告警。 |

## 4. 开发者规则

1. **新增配置项**：在 `config.py` 对应 `BaseSettings` 子类中添加字段，声明 `validation_alias` 和合理默认值，并在 `.env.example` 中补充注释说明。
2. **新增 Provider**：在 `ProvidersConfig` 增加开关，在工厂函数（如 `build_vector_store`）中根据 `providers.normalized()` 分支选择实现。
3. **Go 网关新增配置**：同步修改 `nexus_gate/internal/config/config.go` 的 `Config` 结构体与 `Load()` 中的 `getEnv*` 调用，保持与 Python 共用同一份 `.env`。
4. **路径相关配置**：一律使用 `./xxx` 相对路径格式，交由 `_resolve_path()` 处理，不要硬编码绝对路径。
5. **敏感信息**：永远不要提交 `.env` 到仓库，只提交 `.env.example`；生产环境必须通过 `APP_ENV=prod` 切换到 `.env.prod` 并覆盖所有默认值。
6. **Docker 部署**：宿主机端口映射已在 `docker-compose.yml` 中避让冲突（Redis 16379、MySQL 13306），新增服务需遵循相同健康检查与 `depends_on` 约定。
