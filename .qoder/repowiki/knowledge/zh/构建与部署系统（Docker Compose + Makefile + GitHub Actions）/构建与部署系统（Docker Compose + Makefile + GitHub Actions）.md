---
kind: build_system
name: 构建与部署系统（Docker Compose + Makefile + GitHub Actions）
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - docker-compose.yml
    - docker-compose.dev.yml
    - .github/workflows/ci.yml
    - backend_design/Dockerfile
    - frontend_design/Dockerfile
    - backend_design/nexus_gate/Dockerfile
    - scripts/start-all.ps1
    - backend_design/pyproject.toml
    - backend_design/requirements.txt
    - frontend_design/package.json
    - backend_design/nexus_gate/go.mod
---

## 1. 使用的系统与工具
- **容器编排**：Docker Compose 作为统一编排入口，通过 `docker-compose.yml` 定义应用服务（Go 网关、Python AI 后端、Next.js 前端）与中间件（Milvus、Neo4j、Redis、MySQL、Langfuse、Prometheus、Grafana、Loki），并使用 `profiles: ["app"]` 将应用层与基础设施层解耦。
- **本地开发入口**：根目录 `Makefile` 提供 `install` / `dev` / `test` / `lint` / `docker-up` 等目标，统一封装 Python venv、npm、Go 依赖安装与服务启动。
- **CI/CD**：`.github/workflows/ci.yml` 在 Ubuntu runner 上并行执行三端构建：Python（ruff + pytest）、Go（go vet + go build）、Node（tsc + npm build）。
- **Windows 一键启停**：`scripts/start-all.ps1` 及配套的 `start-backend.ps1` / `start-gateway.ps1` / `start-frontend.ps1` 以 PowerShell 后台进程方式启动各服务并输出到 `logs/{backend,go,frontend}_logs/`。
- **多阶段 Docker 镜像**：后端使用 `python:3.10-slim` 双阶段构建（CPU-only PyTorch 2.5.1），前端使用 `node:18-alpine` 双阶段构建（standalone 模式），网关使用 `golang:1.22-alpine` + `alpine:3.19` 静态编译（`CGO_ENABLED=0`）。

## 2. 核心文件与位置
- `Makefile` — 全局开发/测试/清理入口
- `docker-compose.yml` — 全栈服务编排（含 profiles 分离）
- `docker-compose.dev.yml` — 开发调试覆盖（暴露监控端口、挂载 docs/logs、DEBUG 开关）
- `.github/workflows/ci.yml` — GitHub Actions 流水线
- `backend_design/Dockerfile` — Python AI 后端镜像
- `frontend_design/Dockerfile` — Next.js 前端镜像
- `backend_design/nexus_gate/Dockerfile` — Go 网关镜像
- `scripts/start-all.ps1` 及 `scripts/start-*.ps1` — Windows 启动脚本
- `backend_design/pyproject.toml` / `requirements.txt` — Python 依赖声明
- `frontend_design/package.json` — Node 依赖与构建脚本
- `backend_design/nexus_gate/go.mod` / `go.sum` — Go 模块管理

## 3. 架构与约定
- **分层编排**：`docker-compose.yml` 中基础设施服务（etcd/minio/milvus/neo4j/redis/mysql/langfuse/prometheus/grafana/loki）始终启动；应用服务（nexus_gate/nexus_ai/nexus_frontend）通过 `profiles: ["app"]` 按需拉起，实现开发与交付环境解耦。
- **健康检查**：每个关键服务均定义 `healthcheck`（wget/curl/redis-cli/pg_isready），并通过 `depends_on.condition: service_healthy` 保证启动顺序。
- **环境变量注入**：所有敏感配置通过 `.env` / `env_file` 注入，默认值采用 `${VAR:-default}` 形式，便于本地与 CI 切换。
- **日志聚合**：Loki（`config/loki/loki-config.yml`）+ Prometheus（`config/prometheus/prometheus.yml`）+ Grafana（`config/grafana/provisioning/`）预置数据源与仪表盘，统一可观测性。
- **模型与数据持久化**：`./models:/app/models`、`./data:/app/data`、`./assets:/app/assets` 以卷挂载方式共享，避免镜像膨胀。
- **端口避让**：注释明确标注 Windows Hyper-V 保留端口范围，宿主机映射避开冲突（如 Neo4j 17687、Redis 16379、MySQL 13306）。

## 4. 约定与约束
- **Python 环境**：`make install` 创建 `.venv`，CPU-only PyTorch 通过 `--index-url https://download.pytorch.org/whl/cpu` 安装；GPU 版本由 `make install-gpu` 提供（cu121）。类型检查使用 mypy，代码风格由 ruff 统一。
- **Go 网关**：CI 与 Makefile 均执行 `go vet ./...` 和 `go build ./...`；Dockerfile 强制 `CGO_ENABLED=0 GOOS=linux` 静态编译，确保跨平台二进制。
- **前端构建**：Next.js 使用 standalone 输出（`.next/standalone`），生产镜像仅包含 `server.js` 与静态资源，不携带源码。
- **CI 策略**：Python 任务仅安装轻量依赖运行 `pytest tests/test_v21.py`，mypy 因缺失可选模块（langfuse/redis/openai）在 CI 中跳过，转本地 conda 环境执行。
- **数据库初始化**：`make init-db` 调用 `scripts.init_milvus` 与 `scripts.init_neo4j`；MySQL 通过 `/docker-entrypoint-initdb.d/v2.1_migration.sql` 自动执行迁移。
- **清理约定**：`make clean` 删除 `__pycache__`、`.pytest_cache`、`.mypy_cache`、`.ruff_cache` 以及前端 `.next` 构建产物。
- **开发调试**：`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` 叠加开发覆盖，暴露 Milvus metrics (9201)、Neo4j Browser (17474)、MinIO Console (9001)、Langfuse (3101)、Loki (3100)、Prometheus (9200)、Grafana (3001)。
- **PowerShell 启动规范**：所有 `start-*.ps1` 脚本统一将 stdout/stderr 重定向至 `logs/{service}_logs/service_YYYYMMDD_HHMMSS.log`，并以 `-WindowStyle Hidden` 后台运行。