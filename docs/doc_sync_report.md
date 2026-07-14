# 文档同步检查报告

> 检查时间: 2026-07-11

## 检查概要

- **变更源码文件数**: 14+ (含 30+ 新增文件)
- **变更文档文件数**: 1 (`docs/v2.1-design.md`)
- **关联文档数**: 8
- **一致文档数**: 5
- **需更新文档数**: 3
- **Critical**: 1  |  **Warning**: 2  |  **Info**: 0

## 变更源码文件（主要）

| 文件路径 | 类型 |
|----------|------|
| `backend_design/nexus/main.py` | 修改 |
| `backend_design/nexus/config.py` | 修改 |
| `backend_design/nexus/agent/supervisor_graph.py` | 修改 |
| `backend_design/nexus/models/state.py` | 修改 |
| `backend_design/nexus/core/cockpit_manager.py` | 新增 |
| `backend_design/nexus/core/tenant_context.py` | 新增 |
| `backend_design/nexus/core/db_manager.py` | 新增 |
| `backend_design/nexus/core/voiceprint.py` | 新增 |
| `backend_design/nexus/agent/subagent_monitor.py` | 新增 |
| `backend_design/nexus/agent/mainagent_confirm.py` | 新增 |
| `backend_design/nexus/api/routes/cockpit.py` | 新增 |
| `backend_design/nexus/api/routes/dataplatform.py` | 新增 |
| `backend_design/nexus/api/routes/middleware_status.py` | 新增 |
| `backend_design/nexus/api/routes/settings.py` | 新增 |
| `backend_design/nexus/observability/cockpit_metrics.py` | 新增 |
| `backend_design/nexus/observability/data_retention.py` | 新增 |
| `backend_design/nexus_gate/` (整个 Go 网关) | 新增 |
| `frontend_design/src/stores/auth-store.ts` | 新增 |
| `frontend_design/src/app/dataplatform/` | 新增 |
| `frontend_design/src/app/middleware/` | 新增 |
| `frontend_design/src/lib/api.ts` | 修改 |
| `frontend_design/src/components/layout/sidebar.tsx` | 修改 |
| `docker-compose.yml` | 修改 |
| `config/prometheus/prometheus.yml` | 修改 |

## 需更新文档清单

### 🔴 Critical（文档与代码严重不一致）

| 文档路径 | 问题描述 | 涉及代码 | 已执行操作 |
|----------|----------|----------|----------|
| `docs/PROGRESS.md` | 仍为 v2.0 状态，缺少全部 v2.1 模块、Go 网关、新前端页面、新测试文件 | 全部 v2.1 新增文件 | ✅ 已更新：添加 v2.1 章节、22 个新模块表、Go 网关目录结构 |

### 🟡 Warning（文档缺失或索引过期）

| 文档路径 | 问题描述 | 已执行操作 |
|----------|----------|----------|
| `README.md` | 项目结构缺少 `nexus_gate/` Go 网关目录，缺少新前端页面 | ✅ 已更新：添加 Go 网关到项目结构和技术栈表 |
| `Agent.md` | 目录结构缺少 Go 网关和新 v2.1 模块，查找路径表不完整 | ✅ 已更新：添加 Go 网关目录树、v2.1 新模块路径表 |

## 已检查且一致的文档

- ✅ `docs/v2.1-design.md` — v2.1 设计方案（API 路由清单与实际一致）
- ✅ `docs/architecture/L0-infrastructure.md` — Docker Compose 编排（未涉及 v2.1 变更）
- ✅ `docs/architecture/overview.md` — 7 层架构总览（未涉及 v2.1 变更）
- ✅ `docs/deployment/SETUP.md` — 部署指南（未涉及 v2.1 变更）
- ✅ `docs/testing/TESTING.md` — 测试文档（未涉及 v2.1 变更）

## 文档同步完成摘要

- 自动更新文档: 3 个
- 跳过文档（需人工确认）: 0 个
- 一致文档（无需操作）: 5 个
- 更新详情:
  - ✏️ `docs/PROGRESS.md` — 添加 v2.1 章节、22 个新模块完成表、Go 网关目录结构、新前端页面、v2.1 测试
  - ✏️ `README.md` — 项目结构添加 `nexus_gate/` Go 网关、新前端页面、auth-store/hooks；技术栈表添加 Go 并发网关行
  - ✏️ `Agent.md` — 目录结构添加 Go 网关完整目录树、v2.1 新模块；查找路径表补充 6 个 v2.1 模块路径
