---
kind: configuration_system
name: NexusCockpit 配置系统 — 多语言分层与环境隔离
category: configuration_system
scope:
    - '**'
source_files:
    - backend_design/nexus/config.py
    - backend_design/nexus/main.py
    - backend_design/nexus_gate/internal/config/config.go
    - .env.example
    - frontend_design/.env.local.example
    - docker-compose.yml
---

## 1. 体系概览

NexusCockpit 的配置系统围绕“环境变量 + Pydantic Settings + docker-compose 注入”展开，覆盖 Go 网关、Python AI 后端与 Next.js 前端三个进程。核心设计要点：

- 统一 .env 文件：Go 与 Python 共享项目根目录的 .env（或按 APP_ENV 切换 .env.local / .env.prod），docker-compose 通过 env_file 注入。
- 类型安全加载：Python 侧使用 pydantic-settings.BaseSettings 为每个子系统定义强类型配置类；Go 侧用自定义 getEnv/getEnvInt/getEnvFloat 从 os.Getenv 读取并带默认值。
- 环境隔离与降级开关：通过 ProvidersConfig 的 vector_store/graph_store/cache/reranker 等 provider 字段在 local/cloud/none 间切换，无需改代码即可部署到云端托管服务。
- 运行时单例：Python 通过 @lru_cache 暴露 get_config() 全局单例，避免重复解析 .env。

## 2. 关键文件与包

- Python 配置中心
  - backend_design/nexus/config.py：所有子配置类的集中定义（LLM、Milvus、Neo4j、Redis、MySQL、JWT、Vehicle、ASR/TTS/SV、Langfuse、Server、Tavily、Amap、Providers、Reranker、Memory、Cockpit、Observability）。
  - backend_design/nexus/main.py：应用启动时调用 get_config() 初始化各组件，并将配置注入到 app.state。
- Go 网关配置
  - backend_design/nexus_gate/internal/config/config.go：Config 结构体 + Load()/Get() 单例，仅依赖环境变量。
- 环境变量模板与示例
  - .env.example：完整的环境变量清单，含 LLM、向量库、图谱、缓存、车控、模型路径、双模式 provider、多座舱、LLM 本地降级、记忆管理等全部键。
  - frontend_design/.env.local.example：Next.js 前端专用 NEXT_PUBLIC_* 变量。
- 编排与环境注入
  - docker-compose.yml：为 nexus_gate、nexus_ai、nexus_frontend 分别声明 env_file: .env 与容器内环境变量覆盖（如 REDIS_HOST=redis）。

## 3. 架构与约定

### 3.1 环境变量优先级与加载顺序

1. 选择 .env 文件：根据 APP_ENV 决定加载 .env.prod 或 .env.local，不存在则回退到 .env。
2. 显式 load_dotenv(override=True)：确保目标文件中的值不被其他 .env 覆盖。
3. pydantic-settings 自动读取：每个 BaseSettings 子类通过 model_config = SettingsConfigDict(env_file=_ENV_FILE) 再次绑定同一文件。
4. os.environ 覆盖：容器/宿主直接设置的环境变量优先级最高。

Go 网关不读 .env 文件，只从 os.Getenv 取值，因此必须保证 docker-compose 已将所需键注入到进程环境。

### 3.2 配置分层与命名规范

- 模块级 BaseSettings 类：每个外部依赖或功能域一个类（如 LLMConfig、MilvusConfig、RedisConfig），内部字段通过 Field(..., validation_alias="XXX") 映射到环境变量名。
- 聚合根 AppConfig：包含所有子配置实例，并通过 get_config() 暴露全局单例。
- computed_field 派生属性：如 RedisConfig.url、LLMConfig.embedding_url、AppConfig.project_root，由基础字段计算得出，避免重复拼接。
- 相对路径统一解析：_resolve_path(relative_path) 将 ./models/... 等相对路径解析为基于项目根的绝对路径，确保从任意工作目录启动均可正确定位模型与数据目录。

### 3.3 双模式 Provider 机制

ProvidersConfig 提供四个 provider 开关：
- VECTOR_STORE_PROVIDER: local (Milvus) ↔ cloud (Zilliz)
- GRAPH_STORE_PROVIDER: local (Neo4j) ↔ cloud (AuraDB)
- CACHE_PROVIDER: local (Redis Stack) ↔ cloud (云 Redis)
- RERANKER_PROVIDER: local (BGE) ↔ cloud (硅基流动 Rerank) ↔ none (跳过)

配合 config.py 中对应的工厂函数（如 build_vector_store、build_graph_store）实现零代码改动切换部署目标。

### 3.4 生产安全自检

AppConfig.model_post_init 在生产环境 (APP_ENV=prod) 下检查 JWT 密钥、数据库密码、CORS 等敏感项是否为默认弱值，并在 stderr 输出告警，防止误上线。

### 3.5 前端独立配置

Next.js 前端使用独立的 .env.local，变量必须以 NEXT_PUBLIC_ 前缀开头，构建期注入到浏览器端。与后端共享的 API 地址通过 NEXT_PUBLIC_API_URL 指定。

## 4. 开发者应遵循的规则

1. 新增配置项：在 config.py 对应 BaseSettings 子类中添加字段，使用 validation_alias 映射到 .env.example 中已存在的环境变量名；同步更新 .env.example 注释说明用途与默认值。
2. 路径配置一律相对化：所有模型/数据目录使用以 ./ 开头的相对路径，交由 _resolve_path 解析为绝对路径，禁止硬编码绝对路径。
3. 敏感信息不进仓库：实际密钥填写在 .env（已被 .gitignore 忽略），.env.example 仅保留占位符；生产环境务必修改 JWT_SECRET_KEY、MYSQL_PASSWORD、NEO4J_PASSWORD 等默认值。
4. Provider 切换优先于分支/条件编译：需要接入云端托管服务时，先通过 *_PROVIDER 开关尝试现有 provider，再考虑扩展新的 provider 枚举值。
5. Go 网关环境变量与 Python 保持一致：新增的全局环境变量需同时在 config.go 的 Load() 中补充读取逻辑，并在 docker-compose.yml 中注入到 nexus_gate 服务。
6. 前端变量以 NEXT_PUBLIC_ 前缀：任何需要在浏览器端访问的后端地址都必须以 NEXT_PUBLIC_ 前缀声明，并在 frontend_design/.env.local.example 中记录。
7. 不要绕过 get_config()：业务模块通过 from nexus.config import get_config 获取配置，避免自行解析 .env 导致不一致。