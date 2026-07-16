---
kind: build_system
name: NexusCockpit 多语言工程化构建与编排体系
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
    - .pre-commit-config.yaml
---

## 1. 系统概览
本项目采用 Makefile + Docker Compose + GitHub Actions 三位一体的跨语言构建与编排方案，统一协调 Go（nexus_gate）、Python（FastAPI AI 后端）、TypeScript/Next.js（前端）三个子工程的依赖安装、本地开发、测试、镜像构建与中间件编排。

## 2. 核心文件与职责
- Makefile：顶层入口，封装 install / dev / test / lint / docker-* 等目标，屏蔽 Windows/Linux 路径差异
- docker-compose.yml：声明式编排 nexus_gate、nexus_ai、nexus_frontend 及 etcd/minio/milvus/neo4j/redis/rabbitmq/mysql/loki/prometheus/grafana 等基础设施服务，通过 profiles=["app"] 区分应用层与纯中间件层
- .github/workflows/ci.yml：双 job（backend/frontend）并行执行 ruff+mypy+pytest 与 tsc+build
- backend_design/Dockerfile：Python 多阶段镜像（builder→runner），基于 python:3.11-slim，暴露 8000 端口
- frontend_design/Dockerfile：Next.js 多阶段镜像（node:18-alpine builder→runner），standalone 模式运行
- backend_design/nexus_gate/Dockerfile：Go 单二进制静态编译（CGO_ENABLED=0），alpine runner
- backend_design/pyproject.toml：项目元数据、依赖声明、ruff/mypy/pytest 配置、setuptools 包发现规则
- .pre-commit-config.yaml：提交前自动 ruff --fix + ruff-format（仅 backend_design）

## 3. 架构与约定
- 分层 profiles：docker compose up -d 仅启动中间件；--profile app 才拉起 nexus_gate/nexus_ai/nexus_frontend，便于只调试某一层
- 健康检查贯穿全栈：每个容器均定义 healthcheck（wget/curl/etcdctl/redis-cli/rabbitmq-diagnostics/mysqladmin），compose 用 condition: service_healthy 控制启动顺序
- 端口避让策略：宿主机映射到非默认端口（Redis 16379、MySQL 13306、Grafana 3001），避免与本机已安装服务冲突
- 多阶段镜像最小化：Go 使用 golang:1.22-alpine → alpine:3.19；Python 使用 python:3.11-slim 双层拷贝用户 site-packages；Next.js 使用 node:18-alpine standalone 产物
- 环境变量集中管理：.env 通过 env_file 注入所有服务，关键连接串（MILVUS_URI、NEO4J_URI、REDIS_HOST 等）在 compose 中显式声明
- 数据持久化：所有有状态服务（etcd/minio/milvus/neo4j/redis/rabbitmq/mysql/loki/prometheus/grafana）均挂载命名卷，重启不丢数据
- 数据库迁移即插即用：./backend_design/scripts/v2.1_migration.sql 挂载到 MySQL entrypoint，首次启动自动执行

## 4. 开发者应遵循的规则
- 新增 Python 依赖同时更新 requirements.txt 与 pyproject.toml，确保 CI 与本地环境一致
- 新增 Go 模块后在 backend_design/nexus_gate/go.mod 中声明，Dockerfile 会缓存 go.sum 加速构建
- 新增前端依赖在 frontend_design/package.json 中维护，CI 使用 npm ci 锁定版本
- 修改 compose 服务时同步更新对应服务的 healthcheck 与 depends_on 条件，避免竞态启动
- 本地开发优先使用 make dev / make dev-frontend / make init-db，不要直接手动启动 uvicorn 或 npm run dev
- 提交前确保 pre-commit 钩子通过（ruff --fix），CI 对 lint/type/test/build 均允许失败（|| true），但应修复问题而非忽略错误