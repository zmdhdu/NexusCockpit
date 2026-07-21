---
kind: build_system
name: 构建与制品管理：Makefile + Docker Compose 统一编排
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - docker-compose.yml
    - .github/workflows/ci.yml
    - backend_design/Dockerfile
    - frontend_design/Dockerfile
    - backend_design/nexus_gate/Dockerfile
    - scripts/start-backend.ps1
    - scripts/start-frontend.ps1
    - scripts/start-gateway.ps1
---

## 1. 系统概览
本项目采用 **Makefile 作为统一入口**，组合 **Docker Compose 编排中间件与应用服务**、**GitHub Actions CI**、以及 **PowerShell 本地启动脚本**，形成覆盖“依赖安装 → 开发运行 → 测试检查 → 容器化 → 流水线”的完整构建体系。三个子工程（Go 网关 `backend_design/nexus_gate`、Python AI 后端 `backend_design/nexus`、Next.js 前端 `frontend_design`）各自维护独立构建配置，由根 Makefile 聚合。

## 2. 关键文件与职责
- `Makefile`：所有开发/构建/测试命令的统一入口，定义 install / dev / docker-* / lint / test / check / clean 等目标。
- `docker-compose.yml`：声明式编排 Go 网关、Python 后端、Next.js 前端以及 Milvus/Neo4j/Redis/MySQL/Loki/Prometheus/Grafana 等基础设施，通过 `profiles: ["app"]` 将应用与中间件解耦。
- `backend_design/Dockerfile`：Python 后端多阶段镜像（builder 安装依赖，runner 仅含运行包），暴露 8000 端口并带健康检查。
- `frontend_design/Dockerfile`：Next.js 多阶段镜像，使用 `standalone` 输出以最小化运行时镜像。
- `backend_design/nexus_gate/Dockerfile`：Go 静态编译（`CGO_ENABLED=0`）生成单二进制，基于 `alpine:3.19` 运行。
- `.github/workflows/ci.yml`：三 job 并行执行——Python（ruff + mypy + pytest）、Go（vet + build）、Frontend（tsc --noEmit + npm run build）。
- `scripts/start-{backend,frontend,gateway}.ps1`：Windows 下一键启动各服务并将 stdout/stderr 写入 `logs/{backend,frontend,go}_logs/` 带时间戳日志文件。
- `backend_design/scripts/init_milvus.py` / `init_neo4j.py` / `v2.1_migration.sql`：数据库与向量库初始化脚本，被 `make init-db` 和 compose 自动挂载调用。

## 3. 架构与约定
- **分层构建**：每个子工程独立 Dockerfile，遵循 builder→runner 多阶段模式；Go 强制静态链接避免动态依赖。
- **环境隔离**：Python 使用 venv（`.venv`），前端使用 `node_modules`，Go 使用 `go.mod` 缓存；Compose 通过 `env_file: .env` 共享环境变量。
- **端口避让**：Redis 宿主机映射到 16379、MySQL 到 13306，避开 Windows Hyper-V 保留段及本机已装服务。
- **健康检查**：所有服务在 compose 中定义 healthcheck，应用服务依赖 Redis/Milvus/MySQL 的 `service_healthy` 条件。
- **可观测性内嵌**：Prometheus/Loki/Grafana 随 compose 拉起，Grafana dashboard 通过 `config/grafana/provisioning` 预置。
- **CI 与本地一致**：CI 中的 Python/Go/Node 版本与 Makefile 默认工具链对齐（Python 3.10/3.11、Go 1.22、Node 18/20）。

## 4. 开发者应遵守的规则
- **新增依赖**：Python 改动 `requirements.txt`，Go 改动 `go.mod`，前端改动 `package.json`；确保 `make install-all` 能拉齐。
- **本地开发**：优先使用 `make dev-log` / `make dev-frontend-log` / `make dev-gateway-log` 启动，以便获得结构化日志文件。
- **代码质量**：提交前执行 `make check`（lint + mypy + pytest + go build），CI 会重复相同步骤。
- **容器化**：修改任意 Dockerfile 后，用 `make docker-up` 验证全栈拉起；生产镜像需保持无交互、带 HEALTHCHECK。
- **数据库变更**：新增表结构放入 `backend_design/scripts/v2.1_migration.sql`，compose 会在 MySQL 首次启动时自动执行。
- **环境变量**：新增配置项同步更新 `.env.example` 并在 compose 对应服务的 `environment` 或 `env_file` 中声明。