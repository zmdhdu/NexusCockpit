---
kind: build_system
name: 构建与制品管理 — Makefile + Docker Compose 多服务编排
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
    - backend_design/pyproject.toml
---

## 1. 系统概览
本项目采用「Makefile 统一入口 + docker-compose 编排 + 各语言独立 Dockerfile」的三层构建体系：
- **本地开发**：通过 `make` 目标一键创建 Python/Node 环境、启动前后端 dev server、初始化 Milvus/Neo4j。
- **容器化部署**：docker-compose 将 Go 网关 (NexusGate)、Python AI 后端、Next.js 前端与 Milvus/Neo4j/Redis/MySQL/Loki/Prometheus/Grafana 等中间件统一编排，支持 `--profile app` 按需拉起应用层。
- **CI 流水线**：GitHub Actions 在 push/PR 到 main/develop 时并行执行 Python lint+typecheck+test 与 Node tsc+build，失败不阻断（`|| true`），便于渐进式接入质量门禁。

## 2. 关键文件与职责
| 文件 | 职责 |
|---|---|
| `Makefile` | 统一开发/测试/清理入口；封装 venv 安装、GPU/CPU PyTorch 切换、ruff/mypy/pytest、Docker compose 子命令、数据库初始化 |
| `docker-compose.yml` | 全栈服务编排；定义 profiles(app) 与应用服务、健康检查、端口映射、数据卷挂载、依赖顺序 |
| `backend_design/Dockerfile` | Python 后端多阶段镜像：builder 安装 requirements.txt，runner 仅含运行包，暴露 8000 并 healthcheck `/health` |
| `frontend_design/Dockerfile` | Next.js 多阶段镜像：node:18-alpine builder 执行 `npm run build`，runner 以 `.next/standalone` 模式启动 3000 端口 |
| `backend_design/nexus_gate/Dockerfile` | Go 网关静态编译 (`CGO_ENABLED=0 GOOS=linux`)，alpine runner 仅含二进制与 ca-certificates |
| `backend_design/pyproject.toml` | Python 项目元数据、依赖声明、dev optional-dependencies、ruff/mypy/pytest 配置、setuptools 打包规则 |
| `.github/workflows/ci.yml` | 双 job 并行 CI：backend(Python 3.10, ruff+mypy+pytest) / frontend(Node 20, tsc+build) |
| `backend_design/requirements.txt` | 运行时依赖快照（与 pyproject 同步） |
| `config/prometheus.yml`, `config/grafana/provisioning/*` | Prometheus 抓取与 Grafana Dashboard/DataSource 预置配置 |

## 3. 架构与约定
- **多语言独立构建**：Go/Python/TypeScript 各自维护 Dockerfile，避免跨语言缓存污染；Go 使用静态链接最小镜像，Python 用 `--user` 安装避免 root，Next.js 走 standalone 产物。
- **Profile 分层**：基础设施服务默认启动，应用服务需 `--profile app`，方便单独调试中间件或只跑监控栈。
- **健康检查贯穿**：compose 中每个关键服务均定义 `healthcheck`，应用间 `depends_on.condition=service_healthy` 保证启动顺序。
- **环境变量集中注入**：`.env` 通过 `env_file` 注入所有服务，Go 网关通过 `NEXUS_AI_HOST/PORT` 发现后端，前端通过 `NEXT_PUBLIC_API_URL` 指向网关 8080。
- **版本策略**：pyproject 中 `version = "2.0.0"`，compose 顶部注释标注 `v2.0/v2.1/v2.2` 演进说明（如移除 RabbitMQ/Celery、DB 分区隔离等）。
- **可观测性内嵌**：Prometheus + Loki + Grafana 随 compose 启动，Grafana dashboard 通过 provisioning 自动注册，无需手动登录配置。

## 4. 开发者应遵循的规则
1. **新增依赖**：同时更新 `pyproject.toml` 与 `requirements.txt`（保持同步），并在 `install-gpu`/`install` 目标覆盖 CPU/GPU 两种路径。
2. **新增服务**：在 `docker-compose.yml` 中添加 service 定义、健康检查、端口映射、依赖关系，必要时增加新的 profile。
3. **修改镜像**：为对应语言目录补充/更新 Dockerfile，遵循多阶段构建与最小镜像原则；Go 必须 `CGO_ENABLED=0` 静态编译。
4. **代码质量**：提交前执行 `make check`（ruff + mypy + pytest），CI 已启用但当前为 `|| true` 非阻塞，建议后续改为强制通过。
5. **数据库变更**：SQL 迁移脚本放入 `backend_design/scripts/`，并通过 compose volume 挂载至 MySQL init 目录实现自动执行。
6. **环境变量**：新增配置项优先写入 `.env.example` 并在 compose 相应服务的 `environment` 中显式声明，避免硬编码。