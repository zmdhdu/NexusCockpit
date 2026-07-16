---
kind: configuration_system
name: NexusCockpit 配置系统 — 多语言共享 .env + Pydantic Settings 分层聚合
category: configuration_system
scope:
    - '**'
source_files:
    - backend_design/nexus/config.py
    - backend_design/nexus_gate/internal/config/config.go
    - .env.example
    - docker-compose.yml
    - config/prometheus/prometheus.yml
    - config/grafana/provisioning/dashboards/dashboards.yml
---

## 1. 体系概览

本仓库采用“**单点 .env + 多语言解析**”的配置架构：项目根目录的 `.env`（或按 `APP_ENV` 切换的 `.env.local` / `.env.prod`）是唯一的运行时配置来源，Python 后端与 Go 网关均从同一份环境变量中读取参数，避免配置漂移。

- Python 侧使用 **Pydantic v2 + pydantic-settings** 的 `BaseSettings` 做类型安全、自动校验、默认值与计算字段；
- Go 侧使用自实现的 `os.Getenv` + 类型转换函数，直接读同名环境变量；
- Docker Compose 通过 `env_file: .env` 把宿主机变量注入容器，同时用 `environment:` 覆盖服务发现地址（如 `REDIS_HOST=redis`）。

## 2. 核心文件与职责

| 文件 | 作用 |
|---|---|
| `backend_design/nexus/config.py` | Python 配置中心：所有子配置类（LLM/Redis/Milvus/Neo4j/JWT/Vehicle/ASR/OSS/Langfuse/Server/Tavily/Amap/Providers/Reranker/Data/Cockpit/Observability）+ 全局单例 `get_config()` |
| `backend_design/nexus_gate/internal/config/config.go` | Go 网关配置：`Load()/Get()` 从环境变量加载 Gate/Redis/JWT/RBAC/限流/座舱/声纹等参数 |
| `.env.example` | 完整环境变量模板（含本地/云端双模式开关、v2.1 多座舱、Go 网关等全部键） |
| `docker-compose.yml` | 中间件编排 + 环境变量覆盖（服务间 DNS 名映射）+ `env_file` 注入 |
| `config/prometheus/prometheus.yml` / `config/grafana/provisioning/*.yml` | 可观测性组件静态配置（随 compose 挂载） |

## 3. 加载策略与环境优先级

### 3.1 Python 环境文件选择

```
APP_ENV=prod   → 优先加载 .env.prod
APP_ENV=local  → 优先加载 .env.local
未设置 APP_ENV → 回退到 .env.local，若不存在则回退到 .env
```

在 `config.py` 启动时显式调用 `dotenv.load_dotenv(_ENV_FILE, override=True)`，确保目标文件中的值不会被其他 `.env` 空值覆盖。

### 3.2 环境变量 → Pydantic 字段映射

每个 `BaseSettings` 子类通过 `Field(validation_alias="ENV_KEY")` 声明环境变量名，支持：
- 强类型默认值（如 `int`/`float`/`bool`/`list[str]`）
- `computed_field` 派生 URL（如 `RedisConfig.url`、`LLMConfig.embedding_url`）
- `model_post_init` 自动推导开关（如 `LangfuseConfig.enabled`、`OSSConfig.enabled`）

### 3.3 Go 网关配置

Go 侧不依赖第三方库，`config.Load()` 内硬编码所有键名并调用 `getEnv/getEnvInt/getEnvFloat` 从 `os.Getenv` 取值，提供默认值。键名与 Python 侧一一对应（如 `NEXUS_GATE_HOST`、`JWT_SECRET`、`REDIS_HOST`），保证双进程行为一致。

### 3.4 Docker Compose 注入

- `env_file: .env` 将宿主机 `.env` 注入容器；
- `environment:` 覆盖服务发现地址（如 `REDIS_HOST=redis`、`MILVUS_URI=http://milvus:19530`）；
- 应用服务通过 `depends_on` + `healthcheck` 保证中间件就绪后再启动。

## 4. 设计约定与最佳实践

1. **新增配置项必须三处同步**
   - 在 `config.py` 对应 `BaseSettings` 子类中添加字段（带 `validation_alias`）
   - 在 `.env.example` 中添加注释化的示例键
   - 如需 Go 网关使用，在 `nexus_gate/internal/config/config.go` 的 `Config` 结构体与 `Load()` 中补齐

2. **路径一律相对项目根**
   ASR/TTS/数据目录等使用 `./models/...`、`./data/...` 形式，由 `_resolve_path()` 基于 `__file__` 向上三级定位项目根后拼接绝对路径，确保从任意工作目录启动均可正确解析。

3. **敏感信息走环境变量，禁止硬编码**
   API Key、密码、JWT Secret 等仅出现在 `.env` 及 `.env.example` 的占位符中，生产环境通过 CI/CD 注入，不得提交真实值。

4. **双模式 provider 开关统一入口**
   `ProvidersConfig` 暴露 `vector_store/graph_store/cache/reranker` 四个开关（`local/cloud/none`），配合各子配置类的云端 AK/SK 即可零代码切换部署形态。

5. **生产安全自检**
   `AppConfig.model_post_init` 在 `APP_ENV != "prod"` 时跳过，否则对默认弱密钥、默认数据库密码、通配 CORS 等发出 stderr 警告，阻止误上线。

6. **Go 与 Python 配置键命名对齐**
   网关与 AI 服务共享同一份 `.env`，Go 侧键名（如 `NEXUS_GATE_PORT`、`RBAC_DEFAULT_ROLE`）与 Python 侧保持一致，避免双写两份配置。

## 5. 开发者规则清单

- 新增配置项 → 改 `config.py` + `.env.example` +（如需）`config.go`
- 路径配置 → 使用 `./xxx` 相对路径，交由 `_resolve_path` 解析
- 敏感值 → 只放 `.env`，`.env.example` 仅保留占位符
- 切换部署 → 修改 `*_PROVIDER` 开关 + 对应云端 AK/SK，不改业务代码
- 容器化 → 通过 `docker-compose.yml` 的 `environment:` 覆盖服务发现地址，不要改源码默认值
- 验证 → 启动后检查 `get_config()` 打印的警告信息，确认生产安全项已修正
