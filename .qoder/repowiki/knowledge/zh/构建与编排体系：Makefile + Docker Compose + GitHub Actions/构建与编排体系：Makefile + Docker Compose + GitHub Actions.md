---
kind: build_system
name: 构建与编排体系：Makefile + Docker Compose + GitHub Actions
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - docker-compose.yml
    - .github/workflows/ci.yml
    - backend_design/Dockerfile
    - backend_design/pyproject.toml
    - backend_design/nexus_gate/Dockerfile
    - backend_design/nexus_gate/go.mod
    - frontend_design/Dockerfile
    - frontend_design/package.json
    - backend_design/scripts/v2.1_migration.sql
---

## 1. 使用的系统与工具链
- **统一入口**：根目录 `Makefile` 提供安装、开发、测试、清理等命令，屏蔽后端/前端/基础设施差异。
- **容器编排**：`docker-compose.yml` 定义应用服务（Go Gateway、Python AI、Next.js）和中间件（Milvus、Neo4j、Redis、RabbitMQ、MySQL、Loki、Prometheus、Grafana），通过 `profiles: ["app"]` 将应用与基础设施解耦。
- **镜像构建**：每个子项目独立 `Dockerfile`，全部采用多阶段构建（builder → runner），最小化运行镜像体积。
- **CI 流水线**：`.github/workflows/ci.yml` 在 push/PR 到 main/develop 时并行执行 Python 与 Node 任务，仅做 lint、类型检查与测试，不发布制品。
- **依赖管理**：后端使用 `pyproject.toml`（PEP 621）+ `requirements.txt` 双轨；Go 网关使用 `go.mod`；前端使用 `package.json` + `package-lock.json`。
- **代码质量钩子**：`.pre-commit-config.yaml` 配合 `ruff`、`mypy`、`pytest`，本地提交前自动校验。

## 2. 关键文件与位置
- 根级编排与脚本：`Makefile`、`docker-compose.yml`、`.env.example`、`.pre-commit-config.yaml`
- CI：`.github/workflows/ci.yml`
- 后端 Python：`backend_design/Dockerfile`、`backend_design/pyproject.toml`、`backend_design/requirements.txt`
- Go 网关：`backend_design/nexus_gate/Dockerfile`、`backend_design/nexus_gate/go.mod`
- 前端 Next.js：`frontend_design/Dockerfile`、`frontend_design/package.json`
- 数据库迁移：`backend_design/scripts/v2.1_migration.sql`（由 MySQL 容器启动时自动执行）
- 可观测性配置：`config/prometheus/prometheus.yml`、`config/grafana/provisioning/dashboards.yml`、`config/loki/loki-config.yml`

## 3. 架构与约定
- **分层镜像策略**：Go 网关用 `golang:1.22-alpine` 编译后拷贝二进制到 `alpine:3.19`；Python 后端用 `python:3.11-slim` 分 builder/runner 两阶段；前端用 `node:18-alpine` 构建 `.next/standalone` 产物。所有镜像均暴露健康检查端点供 compose 探测。
- **环境隔离**：应用服务通过 `profiles: ["app"]` 与基础设施服务分离，默认只拉起 etcd/minio/milvus/neo4j/redis/rabbitmq/mysql/loki/prometheus/grafana，需要完整栈时用 `--profile app`。
- **端口避让约定**：宿主机映射避开系统保留段与本机冲突——Redis 16379→6379、MySQL 13306→3306，便于 Windows Hyper-V 和本地已装服务共存。
- **数据持久化**：所有有状态服务通过 named volume 挂载，避免容器重建丢失向量索引、图数据库、消息队列与日志数据。
- **版本与语言基线**：Python ≥3.10（运行时 3.11）、Node 18/20、Go 1.22，均在各自 `Dockerfile` 与 CI 中显式声明，保证可重现。
- **依赖锁定**：前端 `package-lock.json`、Go `go.sum`、Python `requirements.txt` 三套锁文件并存，确保离线/CI 环境一致。

## 4. 开发者应遵循的规则
- **新增依赖**：优先更新对应模块的包清单（`pyproject.toml` / `requirements.txt`、`go.mod`、`package.json`），并同步更新 `install` / `install-gpu` / `install-frontend` 目标，使 `make install-all` 始终可用。
- **编写 Dockerfile**：必须采用多阶段构建，将构建期依赖与运行期镜像分离；为应用服务添加 `HEALTHCHECK`，并在 `docker-compose.yml` 中使用 `depends_on.condition: service_healthy` 建立启动顺序。
- **环境变量**：所有外部配置走 `.env` 或 `environment:` 注入，禁止硬编码；新增变量需同步更新 `.env.example` 与相关服务的 `env_file`。
- **数据库变更**：SQL 迁移放入 `backend_design/scripts/`，并通过 `v2.1_migration.sql` 挂载到 `/docker-entrypoint-initdb.d/` 实现首次启动自动执行；后续增量迁移需在文档中记录。
- **代码质量**：提交前运行 `make check`（ruff + mypy + pytest），建议启用 pre-commit 钩子；CI 对 lint/type/test 使用 `|| true` 降级失败，但本地必须严格通过再合入。
- **可观测性**：新服务如需指标/日志，按现有模式接入 Prometheus exporter 与 Loki，并在 `config/` 下补充对应 provision 配置，保持 Grafana 面板可发现。