---
kind: build_system
name: 构建与制品管理 — Makefile + Docker Compose 多语言编排
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

## 1. 体系概览
本项目以**根级 Makefile**为统一入口，通过 `docker-compose.yml` 编排 Go 网关、Python AI 后端、Next.js 前端以及 Milvus/Neo4j/Redis/MySQL/Grafana/Loki/Prometheus 等基础设施；CI 由 GitHub Actions 驱动，对 Python 与 Node.js 子工程分别执行 lint / type check / test / build。整体采用“本地开发用 venv + npm dev server，容器化用多阶段镜像”的双轨策略。

## 2. 核心文件与职责
- `Makefile`：封装环境安装（CPU/GPU PyTorch）、前后端开发启动、Docker 编排、数据库初始化、代码质量检查（ruff/mypy/pytest）与清理。
- `docker-compose.yml`：定义 `app` profile 下的三个应用服务（nexus_gate/nexus_ai/nexus_frontend）及全部中间件，含健康检查、端口映射与数据卷挂载。
- `backend_design/Dockerfile`：Python 后端多阶段镜像（builder 安装依赖 → runner 运行 uvicorn）。
- `frontend_design/Dockerfile`：Next.js 多阶段镜像（builder 编译 standalone 产物 → runner 仅运行）。
- `backend_design/nexus_gate/Dockerfile`：Go 网关静态编译（CGO_ENABLED=0），最小 alpine 运行镜像。
- `.github/workflows/ci.yml`：push/PR 触发，在 ubuntu-latest 上并行跑 backend/frontend 两个 job。
- `scripts/start-*.ps1`：Windows 下带完整日志捕获的启动脚本，配合 `make dev-log|dev-frontend-log|dev-gateway-log` 使用。

## 3. 架构与约定
- **多语言分层**：Go 网关负责鉴权/限流/WebSocket 转发，Python FastAPI 承载 Agent/RAG/TTS/ASR 推理，Next.js 提供控制台 UI。
- **依赖隔离**：后端使用 venv + requirements.txt（另附 `requirements_no_torch.txt` 供无 GPU 场景），前端使用 `package.json` + `npm ci`；两者均通过独立 Dockerfile 多阶段构建，避免 builder 污染运行镜像。
- **服务发现与配置**：应用间通过 docker-compose 内部 DNS（如 `nexus_ai:8000`、`redis:6379`）通信，环境变量统一从根 `.env` 注入；宿主机端口避让 Windows Hyper-V 保留段（Redis→16379、MySQL→13306）。
- **可观测性内嵌**：Grafana/Prometheus/Loki 随 compose 拉起，Grafana dashboard 与 Prometheus scrape 配置位于 `config/` 目录并 volume 挂载。
- **版本演进标记**：Compose 与 Dockerfile 注释中带有 `v2.x` 标记（如移除 RabbitMQ/Celery、简化 Redis 端口），体现渐进式重构轨迹。

## 4. 开发者应遵循的规则
- **新增依赖**：后端改动须同步更新 `backend_design/requirements.txt`（或 `pyproject.toml` 的 `[project]` 依赖区），确保 `make install` 与 CI 一致；前端依赖变更需反映在 `frontend_design/package.json` 且能 `npm ci` 成功。
- **新增服务**：在 `docker-compose.yml` 中声明 service、healthcheck、ports/volumes，并在 `Makefile` 暴露对应 target（如 `docker-up`/`docker-down`）。
- **镜像构建**：遵循多阶段模式，将编译期依赖放在 builder 阶段，runner 镜像仅包含运行时二进制与必要证书；Go 服务保持 `CGO_ENABLED=0` 以获得静态二进制。
- **测试与质量门禁**：所有提交会触发 CI，务必保证 `ruff check`、`mypy --ignore-missing-imports`、`pytest`、`tsc --noEmit` 与 `npm run build` 均能通过；本地可用 `make check` 一键复现。
- **Windows 开发**：优先使用 `make dev-log|dev-frontend-log|dev-gateway-log` 调用 PowerShell 启动脚本，以便统一收集日志到 `logs/{backend,frontend,go}_logs/`。
- **数据库初始化**：首次运行后执行 `make init-db` 完成 Milvus/Neo4j 初始化；MySQL 迁移脚本通过 `/docker-entrypoint-initdb.d/` 自动执行，后续增量迁移应追加至该目录。