---
kind: configuration_system
name: NexusCockpit 配置系统 — 基于 Pydantic Settings 的多环境分层配置
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
---

## 1. 系统与工具

- Python 后端使用 Pydantic v2 + pydantic-settings 实现类型安全的集中式配置，所有子模块通过 get_config() 单例访问。
- Go 网关（nexus_gate）采用手写 os.Getenv + 默认值的方式独立加载环境变量，与 Python 共享同一份 .env 文件。
- 前端 Next.js 使用独立的 .env.local（以 NEXT_PUBLIC_ 前缀暴露给浏览器）。
- 容器编排通过 docker-compose.yml 的 env_file: .env 将根目录配置注入各服务。

## 2. 核心文件与包

- backend_design/nexus/config.py — Python 配置中心，定义所有 BaseSettings 子类及全局 AppConfig、get_config()。
- backend_design/nexus_gate/internal/config/config.go — Go 网关配置加载，从环境变量读取并构造 Config 结构体。
- frontend_design/.env.local.example — 前端环境变量模板。
- 根目录 .env / .env.example — 统一的环境变量清单与注释说明。
- docker-compose.yml — 通过 env_file 和 environment 向各容器注入配置。

## 3. 架构与环境分层

### 3.1 多环境文件选择策略

Python 端在启动时根据 APP_ENV 决定加载哪个 .env 文件：
- APP_ENV=prod → 优先加载 .env.prod，不存在则回退到 .env.local → .env
- APP_ENV=local（默认）→ 优先加载 .env.local，不存在则回退到 .env

加载顺序为：先显式 dotenv.load_dotenv(_ENV_FILE, override=True) 把目标文件写入 os.environ，再由 pydantic-settings 读取，避免多个 .env 互相覆盖。

### 3.2 配置层次结构

AppConfig (聚合入口)
├── LLMConfig          # ARK API Key、模型名、温度、超时、本地降级等
├── MilvusConfig       # 向量库 host/port/URI/token/collection
├── Neo4jConfig        # 图谱数据库 URI/user/password
├── RedisConfig        # 缓存/限流/语义缓存参数
├── MySQLConfig        # 用户数据持久化
├── JWTConfig          # Token 签名密钥与过期时间
├── VehicleConfig      # mock/http/mcp 车控适配器
├── ASRConfig          # FunASR/CAM++/CosyVoice 模型路径
├── LangfuseConfig     # LLM 链路追踪（自动启用判断）
├── ObservabilityConfig# Prometheus/Grafana 地址
├── ServerConfig       # FastAPI host/port/debug/log_level
├── TavilyConfig       # 联网搜索
├── AmapConfig         # 高德地图逆地理编码
├── ProvidersConfig    # local/cloud provider 开关
├── RerankerConfig     # 重排器模型 ID
└── CockpitSettings    # 多座舱数量、Go 网关地址、RBAC、声纹阈值

每个子配置类都声明 model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")，并通过 validation_alias 映射到 .env 中的大写键名。

### 3.3 路径解析约定

所有相对路径（如 ./models/asr/sensevoice）通过 _resolve_path() 基于项目根目录（config.py 向上三级）解析为绝对路径，确保无论从哪里启动都能正确定位。

### 3.4 Go 网关配置差异

Go 侧未使用 pydantic-settings，而是直接 os.Getenv("NEXUS_GATE_HOST", "0.0.0.0") 等硬编码默认值，字段命名与 Python 侧不完全一致（例如 JWT_SECRET vs JWT_SECRET_KEY），但两者均从同一个 .env 文件读取。

### 3.5 双模式部署开关

通过 ProvidersConfig 的四个开关控制中间件来源：
- VECTOR_STORE_PROVIDER=local|cloud
- GRAPH_STORE_PROVIDER=local|cloud
- CACHE_PROVIDER=local|cloud
- RERANKER_PROVIDER=local|cloud|none

配合 LLM_FALLBACK_* 系列变量实现云端 LLM 不可用时的本地 llama.cpp 降级。

### 3.6 生产安全自检

AppConfig.model_post_init 在生产环境 (APP_ENV=prod) 下检查默认弱密钥（JWT、MySQL、Neo4j 密码、CORS *），并在 stderr 输出告警。

## 4. 开发者应遵循的规则

1. 新增配置项：在 config.py 中新增一个 BaseSettings 子类，使用 Field(default=..., validation_alias="ENV_KEY") 声明，并在 AppConfig 中聚合。
2. 环境变量命名：保持全大写蛇形（如 ARK_API_KEY），与 .env.example 保持一致。
3. 相对路径一律走 _resolve_path：不要直接使用 os.path.join 拼接工作目录。
4. 敏感信息不进仓库：.env 已加入 .gitignore，只提交 .env.example；生产使用 .env.prod 或 CI 注入。
5. Go 与 Python 共用 .env：新增的全局变量需同时在两处添加对应读取逻辑，避免不一致。
6. Docker 部署：通过 docker-compose.yml 的 env_file: .env 注入，必要时在 environment: 中覆盖容器内主机名（如 REDIS_HOST=redis）。
7. 前端配置隔离：前端仅使用 frontend_design/.env.local，且必须以 NEXT_PUBLIC_ 前缀暴露给浏览器。