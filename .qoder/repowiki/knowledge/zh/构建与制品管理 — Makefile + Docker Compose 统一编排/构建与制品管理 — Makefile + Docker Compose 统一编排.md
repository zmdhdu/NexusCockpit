---
kind: build_system
name: 构建与制品管理 — Makefile + Docker Compose 统一编排
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - docker-compose.yml
    - backend_design/Dockerfile
    - backend_design/nexus_gate/Dockerfile
    - frontend_design/Dockerfile
    - .github/workflows/ci.yml
    - backend_design/requirements.txt
    - frontend_design/package.json
    - backend_design/nexus_gate/go.mod
    - scripts/start-backend.ps1
    - scripts/start-frontend.ps1
    - scripts/start-gateway.ps1
---

## 1. 使用的系统与工具链

- **顶层装配层**：`Makefile` 作为统一入口，封装 Python/Node.js/Go 三端依赖安装、开发启动、测试、清理以及 Docker 编排命令。
- **容器编排**：`docker-compose.yml` 定义应用服务（Go 网关 `nexus_gate`、Python AI 后端 `nexus_ai`、Next.js 前端 `nexus_frontend`）与中间件（Milvus、Neo4j、Redis Stack、MySQL、Loki、Prometheus、Grafana），通过 `profiles: ["app"]` 将应用与基础设施解耦。
- **镜像构建**：每个子项目提供独立 `Dockerfile`，全部采用**多阶段构建**（builder → runner），最小化运行镜像体积。
- **CI 流水线**：`.github/workflows/ci.yml` 在 push/pull_request 到 main/develop 时触发，分别对 backend 和 frontend 执行 lint、类型检查与测试；Go 网关未纳入 CI。
- **本地调试脚本**：`scripts/start-backend.ps1`、`start-frontend.ps1`、`start-gateway.ps1` 配合 `make dev-log` / `dev-frontend-log` / `dev-gateway-log` 实现 Windows 下带日志文件捕获的开发启动。

## 2. 关键文件与位置

| 角色 | 路径 |
|---|---|
| 顶层装配 | `Makefile` |
| 容器编排 | `docker-compose.yml` |
| Python 后端镜像 | `backend_design/Dockerfile` |
| Go 网关镜像 | `backend_design/nexus_gate/Dockerfile` |
| Next.js 前端镜像 | `frontend_design/Dockerfile` |
| CI 流水线 | `.github/workflows/ci.yml` |
| 依赖清单 | `backend_design/requirements.txt`、`frontend_design/package.json`、`backend_design/nexus_gate/go.mod` |
| 本地启动脚本 | `scripts/start-backend.ps1`、`scripts/start-frontend.ps1`、`scripts/start-gateway.ps1` |
| 环境变量模板 | `.env.example`、`.env` |

## 3. 架构与约定

### 3.1 分层职责
- **Makefile**：只暴露目标（install / dev / test / docker-* / check / clean），不直接写语言细节；所有语言特定逻辑下沉到各子项目的 `Dockerfile`、`package.json`、`go.mod`。
- **docker-compose.yml**：按“应用服务”和“基础设施服务”分组，应用服务统一走 `profiles: ["app"]`，默认仅拉起中间件；通过 `depends_on` + `healthcheck` 保证启动顺序。
- **Dockerfile**：遵循 builder→runner 两阶段模式，Go 使用 `CGO_ENABLED=0 GOOS=linux` 静态编译，Python 用 `pip install --user` 并复制 `/root/.local`，Node 用 `npm ci` 并利用缓存。

### 3.2 端口与环境隔离
- 宿主机端口避让本机冲突：Redis 16379、MySQL 13306、Grafana 3001、Prometheus 9200、Loki 3100。
- 应用间通信通过 compose 内部 DNS（如 `NEXUS_AI_HOST=nexus_ai`、`REDIS_HOST=redis`），避免硬编码 localhost。
- 共享配置集中放在根目录 `.env`，由 `env_file` 注入各服务。

### 3.3 数据持久化
- 所有有状态中间件（etcd、minio、milvus、neo4j、redis、mysql、prometheus、grafana、loki）均声明独立 named volume，重启不丢数据。
- 模型权重与运行时数据通过 bind mount 挂载：`./models:/app/models`、`./data:/app/data`、`./assets:/app/assets`、`./docs:/app/docs`。

### 3.4 版本与发布策略
- 版本号以注释形式标注在各 Dockerfile 与 compose 头部（如 `v2.1`、`v2.0`），未见统一的 `VERSION` 文件或 tag 生成规则。
- 当前仓库未包含 release 打包或制品上传步骤，主要面向开发与联调场景。

## 4. 开发者应遵守的规则

1. **新增服务必须三件套齐全**：在 `docker-compose.yml` 中注册服务、编写对应 `Dockerfile`、在 `Makefile` 暴露 `docker-*` 目标，并在 `.github/workflows/ci.yml` 补充相应 job。
2. **保持多阶段构建**：新镜像一律采用 builder→runner 两阶段，确保运行镜像不含构建期依赖。
3. **健康检查不可省略**：compose 中的 `depends_on.condition: service_healthy` 依赖 `HEALTHCHECK`，新增服务需同时定义。
4. **端口避让原则**：宿主机映射端口不得与本机常用端口冲突，参考 Redis 16379、MySQL 13306 的命名习惯。
5. **环境变量来源单一**：优先使用 `env_file: .env`，仅在 compose 内需要覆盖时才写 `environment:` 字段。
6. **数据卷规范**：任何有状态服务必须声明 named volume，bind mount 仅限开发期临时数据（如 `./models`、`./data`）。
7. **CI 与本地一致**：CI 中使用的 Python 3.10、Node 20 应与本地开发环境保持一致，避免“本地能跑、CI 挂掉”。
8. **Windows 开发**：使用 `make dev-log` 等 PowerShell 包装目标，不要直接调用 uvicorn/npm 启动，以便统一落盘日志到 `logs/{backend,frontend,go}_logs/`。
