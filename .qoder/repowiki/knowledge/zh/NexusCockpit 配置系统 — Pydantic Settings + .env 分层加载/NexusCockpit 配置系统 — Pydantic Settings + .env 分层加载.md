---
kind: configuration_system
name: NexusCockpit 配置系统 — Pydantic Settings + .env 分层加载
category: configuration_system
scope:
    - '**'
source_files:
    - backend_design/nexus/config.py
    - backend_design/nexus_gate/internal/config/config.go
    - .env.example
    - frontend_design/.env.local.example
    - docker-compose.yml
---

## 1. 系统概览

NexusCockpit 采用 Pydantic Settings + .env 文件作为统一配置方案，Go 网关与 Python AI 后端共享同一份 .env 环境变量体系。配置按环境分层（local/prod），并通过 APP_ENV 自动切换，所有路径基于项目根目录解析，确保容器化部署可移植性。

## 2. 核心组件

Python 后端配置中心 (backend_design/nexus/config.py):
- 使用 pydantic_settings.BaseSettings 实现类型安全的配置管理
- 通过 validation_alias 将环境变量映射到字段名
- 提供全局单例 get_config() 供各模块访问
- 支持 computed_field 派生配置（如 Redis URL、Embedding URL）

Go 网关配置 (backend_design/nexus_gate/internal/config/config.go):
- 从环境变量直接读取，与 Python 共享 .env 文件
- 提供 Load() / Get() 获取全局配置
- 包含网关、JWT、Redis、RBAC、座舱等独立配置项

前端配置 (frontend_design/.env.local.example):
- Next.js 专用环境变量，以 NEXT_PUBLIC_ 前缀暴露给浏览器
- 独立于后端配置，指向网关地址

## 3. 环境分层策略

APP_ENV=prod → .env.prod (生产)
APP_ENV=local → .env.local (开发默认)
未设置 → .env.local (回退)
.env.local 不存在 → .env (兼容旧逻辑)

优先级：环境变量 > .env 文件 > 默认值

## 4. 配置分类

LLM/Embedding: LLMConfig - ARK_API_KEY, ARK_BASE_URL, LLM_MODEL
向量数据库: MilvusConfig - MILVUS_HOST, MILVUS_URI, COLLECTION_*
知识图谱: Neo4jConfig - NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
缓存/限流: RedisConfig - REDIS_HOST, SEMANTIC_CACHE_*
关系数据库: MySQLConfig - MYSQL_HOST, MYSQL_DATABASE
认证: JWTConfig - JWT_SECRET_KEY, JWT_EXPIRE_MINUTES
车控总线: VehicleConfig - VEHICLE_ADAPTER, VEHICLE_API_*
语音模型: ASRConfig - FUNASR_MODEL_PATH, CAM_MODEL_PATH, COSYVOICE_MODEL_PATH
数据目录: DataConfig - FOOD_DATA_DIR, KNOWLEDGE_DATA_DIR, UPLOAD_DIR
双模式部署: ProvidersConfig - VECTOR_STORE_PROVIDER, GRAPH_STORE_PROVIDER
可观测性: ObservabilityConfig - PROMETHEUS_URL, GRAFANA_URL
多座舱: CockpitSettings - COCKPIT_COUNT, RBAC_DEFAULT_ROLE

## 5. 架构约定

路径解析: 所有相对路径通过 _resolve_path() 基于项目根目录解析，避免工作目录依赖
安全校验: 生产环境启动时检查弱密钥并输出警告
Provider 抽象: 通过 ProvidersConfig 控制本地/云端服务切换，无需修改代码
降级机制: LLM_FALLBACK_* 支持云端不可用时自动降级到本地 llama.cpp

## 6. 开发者规范

新增配置必须定义在 config.py 对应配置类中，使用 Field(default=..., validation_alias="ENV_VAR")
敏感信息放入 .env，模板放入 .env.example
路径配置使用相对路径（以 ./ 开头），由 _resolve_path() 解析
生产环境必须覆盖所有默认密码和密钥
前端配置使用 NEXT_PUBLIC_ 前缀，仅暴露必要接口地址