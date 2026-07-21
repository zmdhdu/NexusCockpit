---
kind: configuration_system
name: NexusCockpit 配置系统 — Pydantic Settings + 环境变量分层加载
category: configuration_system
scope:
    - '**'
source_files:
    - backend_design/nexus/config.py
    - backend_design/nexus_gate/internal/config/config.go
    - .env.example
    - .env
    - frontend_design/.env.local.example
    - docker-compose.yml
    - config/prometheus/prometheus.yml
    - config/grafana/provisioning/dashboards.yml
    - config/loki/loki-config.yml
---

## 1. 整体方案

NexusCockpit 采用 **Pydantic Settings（Python）+ Go 原生 `os.Getenv`（Go 网关）** 的双语言配置体系，通过 `.env` 文件与环境变量实现统一注入。核心设计：

- **单一事实源**：所有运行时参数集中声明在 `backend_design/nexus/config.py` 的 `AppConfig` 聚合类中，每个子系统一个 `BaseSettings` 子类。
- **环境文件自动切换**：根据 `APP_ENV=local|prod` 选择 `.env.local` / `.env.prod`，不存在时回退到根目录 `.env`；使用 `dotenv.load_dotenv(override=True)` 显式加载，避免 pydantic-settings 被多个 .env 干扰。
- **类型安全 + 默认值**：每个字段用 `Field(default=..., validation_alias="ENV_KEY")` 声明，未设置时提供开发友好的默认值。
- **全局单例**：`get_config()` 通过 `@lru_cache(maxsize=1)` 缓存，应用生命周期内只读取一次 .env。
- **生产安全检查**：`AppConfig.model_post_init` 在 `APP_ENV=prod` 时拒绝弱密钥、通配符 CORS 等不安全配置。

Go 网关 (`nexus_gate/internal/config/config.go`) 复用同一份 `.env` 中的 `NEXUS_GATE_*`、`JWT_SECRET`、`REDIS_*` 等键，并通过 `validateProdSecurity` 与 Python 侧对齐安全策略。

## 2. 关键文件与包

| 层级 | 路径 | 职责 |
|---|---|---|
| Python 配置中心 | `backend_design/nexus/config.py` | 全部配置模型、环境文件加载、全局单例、生产安全检查 |
| Go 网关配置 | `backend_design/nexus_gate/internal/config/config.go` | 网关/鉴权/Redis/RBAC 等配置加载与校验 |
| 环境变量模板 | `.env.example` | 完整可复制的环境变量清单（含注释说明） |
| 本地开发模板 | `.env` | 备份/模板，实际由 `.env.local` 或 `.env.prod` 覆盖 |
| 前端配置 | `frontend_design/.env.local.example` | Next.js 构建期常量 `NEXT_PUBLIC_API_URL` |
| 编排注入 | `docker-compose.yml` | 为各服务注入容器网络名（如 `redis`、`milvus`）并挂载数据卷 |
| 可观测性配置 | `config/prometheus/prometheus.yml`、`config/grafana/provisioning/*.yml`、`config/loki/loki-config.yml` | Prometheus/Grafana/Loki 独立配置文件，由 compose 挂载 |

## 3. 架构与约定

### 3.1 配置分层

```
AppConfig (聚合根)
├── LLMConfig          → ARK_API_KEY, ARK_BASE_URL, LLM_MODEL, EMBEDDING_*, FALLBACK_*
├── MilvusConfig       → MILVUS_HOST/PORT/URI/TOKEN, COLLECTION_*
├── Neo4jConfig        → NEO4J_URI/USER/PASSWORD
├── RedisConfig        → REDIS_HOST/PORT/PASSWORD/DB + SEMANTIC_CACHE_*
├── MySQLConfig        → MYSQL_HOST/PORT/USER/PASSWORD/DATABASE
├── JWTConfig          → JWT_SECRET_KEY, ALGORITHM, EXPIRE_MINUTES
├── VehicleConfig      → VEHICLE_ADAPTER/http/mcp 三模式
├── ASRConfig          → FUNASR/CAM/COSYVOICE 模型路径 + 声纹音频目录
├── DataConfig         → food/knowledge/uploads/temp/preferences 数据目录
├── LangfuseConfig     → public_key/secret_key/host (空则禁用)
├── ObservabilityConfig→ PROMETHEUS_URL, GRAFANA_URL
├── ServerConfig       → HOST/PORT/DEBUG/LOG_LEVEL/CORS_ORIGINS
├── ProvidersConfig    → VECTOR_STORE_PROVIDER / GRAPH_STORE_PROVIDER / CACHE_PROVIDER / RERANKER_PROVIDER
├── RerankerConfig     → RERANK_MODEL
├── MemoryConfig       → MEMORY_COMPRESS_THRESHOLD_TURNS / KEEP_RECENT_TURNS / MAX_SUMMARY_CHARS / ...
└── CockpitSettings    → COCKPIT_COUNT, NEXUS_GATE_*, RBAC_*, VOICEPRINT_*
```

### 3.2 路径解析约定

所有相对路径（模型、数据、音频）以 `./models/...`、`./data/...`、`./assets/...` 形式声明，通过 `_resolve_path()` 基于项目根目录拼接绝对路径，确保从任意工作目录启动均可正确定位。

### 3.3 Provider 双模式开关

`ProvidersConfig` 暴露四个 provider 开关：
- `VECTOR_STORE_PROVIDER`: local=本地 Milvus | cloud=Zilliz Cloud
- `GRAPH_STORE_PROVIDER`: local=本地 Neo4j | cloud=AuraDB
- `CACHE_PROVIDER`: local=本地 Redis Stack | cloud=云 Redis
- `RERANKER_PROVIDER`: local=本地 BGE | cloud=硅基流动 Rerank | none=跳过

仅改 .env 即可切换后端依赖，代码无需改动。

### 3.4 环境变量优先级

1. 进程级 `os.environ`（最高）
2. 目标 .env 文件（`.env.local` / `.env.prod`，由 `APP_ENV` 决定）
3. 回退 `.env`
4. `Field(default=...)` 默认值

### 3.5 生产安全拦截

| 检查项 | Python 侧 | Go 侧 |
|---|---|---|
| JWT 弱密钥 | `JWT_SECRET_KEY != "change-me-in-production"` | `JWT_SECRET != "nexus-cockpit-secret"` |
| CORS 通配符 | `cors_origins != ["*"]` | `CORS_ORIGINS != "*"` |
| 默认数据库密码 | 告警（不阻止） | 无 |
| 普通用户口令 | 无 | `RBAC_USER_PASSWORD` 非空 |

任一 P0 失败直接 `raise ValueError` / `log.Fatalf` 拒绝启动。

## 4. 开发者应遵循的规则

1. **新增配置项**：在 `config.py` 对应 `BaseSettings` 子类中添加 `Field(default=..., validation_alias="ENV_KEY")`，并在 `.env.example` 补充注释。
2. **不要硬编码路径**：所有磁盘路径必须走 `DataConfig` / `ASRConfig` 的 resolved_* 方法，禁止在业务代码里写死 `./models/...`。
3. **敏感信息不进仓库**：API Key、密码放入 `.env.local` / `.env.prod`，`.gitignore` 已排除这些文件。
4. **生产部署前**：确认 `APP_ENV=prod` 下所有 P0 检查通过，特别是 JWT Secret、CORS Origins、RBAC User Password。
5. **Provider 切换**：修改 `*_PROVIDER` 开关后，确保对应的云端 AK/SK 已在 .env 中填写。
6. **Go 网关新增配置**：同步在 `nexus_gate/internal/config/config.go` 的 `Config` 结构体与 `Load()` 中声明，保持键名一致。
7. **Docker 注入**：如需新环境变量，在 `docker-compose.yml` 的 `environment:` 段注入容器网络名（如 `MILVUS_HOST=milvus`），宿主机端口映射已在 compose 中处理。
