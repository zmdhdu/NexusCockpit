---
name: doc-sync
description: 代码修改完成后自动调用，检查项目中所有 .md 文档是否与最新代码保持一致。识别过期文档并生成同步更新建议，确保文档与代码永不脱节。
---

## 权威入口

- `.catpaw/skills/doc-sync/SKILL.md`

## 适用场景

- **每次代码修改完成后自动触发**（作为收尾步骤，类似 code-review / change-impact-report）
- Agent 修改了 `.py` / `.ts` / `.tsx` 等源码后，检查关联的 `.md` 文档是否需要同步
- 新增文件后检查文档索引（如 `PROGRESS.md`、`README.md`、`architecture/README.md`）是否需要补充
- 删除/重命名文件后检查文档中的引用是否过期
- 主动整理项目文档体系，发现文档与代码不一致的"债务"

## 非适用场景

- 不用于替代代码注释（那是 `code-doc` skill 的职责）
- 不用于编写全新文档（仅同步已有文档）
- 不用于变更影响评估（那是 `change-impact-report` skill 的职责）

## 执行步骤

### 第 1 步：识别变更范围

使用 `git diff --name-only HEAD~1`（或当前未提交的 `git diff --name-only`）获取本次修改的文件列表。
将变更文件分为三类：
- **源码变更**：`.py` / `.ts` / `.tsx` / `.js` / `.jsx` / `.go` / `.rs` 等
- **文档变更**：`.md` 文件
- **配置变更**：`.yaml` / `.yml` / `.toml` / `.json` / `.env` / `Makefile` / `Dockerfile` 等

### 第 2 步：查找关联文档

读取 `.catpaw/skills/doc-sync/doc_mapping.yaml`，将每个变更的源码文件路径与映射表匹配，找到关联的文档文件。

映射规则：
- **精确路径匹配**：文件路径完全匹配 `code_path` 字段
- **前缀匹配**：文件路径以 `code_prefix` 开头（如 `nexus/middleware/` 匹配 `nexus/middleware/redis_cache.py`）
- **兜底规则**：未匹配到的变更，根据目录结构推断关联文档（如 `nexus/agent/` → `L4-agent.md`）

### 第 3 步：逐文档检查一致性

对每个关联文档，按以下维度检查：

| 检查维度 | 具体内容 |
|----------|----------|
| **文件清单** | 文档中提到的文件路径是否仍然存在？是否有新增文件未在文档中登记？ |
| **函数/类签名** | 文档中引用的函数名、参数列表、返回值是否与代码一致？ |
| **路由表** | API 文档中的路由清单是否与 `@router` 装饰器一致？ |
| **配置项** | 文档中列出的配置参数是否与 `config.py` 中的字段一致？ |
| **依赖列表** | 文档中提到的依赖是否与 `requirements.txt` / `package.json` 一致？ |
| **进度状态** | `PROGRESS.md` 中的模块完成状态是否反映最新代码状态？ |
| **Skills 清单** | `architecture/README.md` 中的 Skills 表格是否包含所有 skill？ |

### 第 4 步：生成同步报告

输出结构化 Markdown 报告，按严重程度分级：

```markdown
# 文档同步检查报告

## 检查概要
- **检查时间**: YYYY-MM-DD HH:MM:SS
- **变更文件数**: N 个源码 + M 个文档
- **关联文档数**: K 个文档需检查
- **一致文档数**: J 个
- **需更新文档数**: P 个

## 需更新文档清单

### 🔴 Critical（文档与代码严重不一致）

| 文档路径 | 问题描述 | 涉及代码 | 建议操作 |
|----------|----------|----------|----------|
| docs/architecture/L5-middleware.md | redis_cache.py 的 set() 新增 has_side_effect 参数，文档未记录 | middleware/redis_cache.py:140 | 补充参数说明和安全设计章节 |

### 🟡 Warning（文档缺失或索引过期）

| 文档路径 | 问题描述 | 建议操作 |
|----------|----------|----------|
| docs/PROGRESS.md | 新增 core/auth.py 和 middleware/session_store.py 未登记 | 在后端模块完成详情表中补充两行 |

### 🟢 Info（建议优化）

| 文档路径 | 问题描述 | 建议操作 |
|----------|----------|----------|
| docs/architecture/L6-api.md | 路由清单缺少 POST /auth/token | 补充认证路由行 |

## 已检查且一致的文档

- ✅ docs/architecture/L1-core.md — 与 core/ 目录一致
- ✅ docs/architecture/L4-agent.md — 与 agent/ 目录一致
```

### 第 5 步：执行同步更新（自动模式）

如果检查发现需更新的文档，**直接修改文档使其与代码一致**，而非仅提供建议。更新原则：
- **新增文件**：在文档对应章节的文件清单中补充
- **签名变更**：更新文档中的函数签名/参数列表
- **路由变更**：更新路由表格
- **进度变更**：更新 PROGRESS.md 中的状态和百分比
- **Skills 变更**：更新 architecture/README.md 的 Skills 表格
- 更新文档顶部的 `最后更新` 日期为当天

### 第 6 步：输出最终摘要

```markdown
## 文档同步完成摘要
- 自动更新文档: X 个
- 跳过文档（需人工确认）: Y 个
- 一致文档（无需操作）: Z 个
- 更新详情:
  - ✏️ docs/architecture/L5-middleware.md — 补充 has_side_effect 参数说明
  - ✏️ docs/PROGRESS.md — 新增 auth.py 和 session_store.py 模块登记
  - ✏️ docs/architecture/L6-api.md — 补充 /auth/token 路由
```

## 代码-文档映射表

映射表维护在 `.catpaw/skills/doc-sync/doc_mapping.yaml` 中，格式如下：

```yaml
mappings:
  # 精确路径映射
  - code_path: "backend_design/nexus/main.py"
    docs:
      - "docs/architecture/L6-api.md"
      - "docs/PROGRESS.md"

  # 前缀映射（匹配目录下所有文件）
  - code_prefix: "backend_design/nexus/middleware/"
    docs:
      - "docs/architecture/L5-middleware.md"
      - "docs/PROGRESS.md"

  # 特殊映射：配置文件变更影响多个文档
  - code_path: "backend_design/requirements.txt"
    docs:
      - "docs/deployment/SETUP.md"
      - "docs/PROGRESS.md"
```

## 文档体系全景

项目文档按以下层级组织，每层文档对应特定的代码模块：

```
docs/
├── architecture/
│   ├── README.md              ← 文档索引（总入口）
│   ├── overview.md            ← 7层架构总览
│   ├── L0-infrastructure.md   ← Docker / 基础设施
│   ├── L1-core.md             ← nexus/core/ (config/logger/exceptions/auth/oss)
│   ├── L2-data.md             ← nexus/rag/ + nexus/memory/
│   ├── L3-service.md          ← nexus/asr/ + nexus/tts/ + nexus/skills/ + nexus/vehicle/
│   ├── L4-agent.md            ← nexus/agent/ + nexus/intent/
│   ├── L5-middleware.md       ← nexus/middleware/ (cache/ratelimiter/taskqueue/session)
│   ├── L6-api.md              ← nexus/api/ + nexus/main.py
│   ├── L7-observability.md    ← nexus/observability/ (langfuse/metrics)
│   ├── structure.md           ← 全景架构文档
│   ├── gap_analysis.md        ← 差距分析
│   ├── v2.0_improve.md        ← v2.0 改进方案
│   └── vehicle_agent_*.md     ← 深度方案文档
├── deployment/
│   ├── SETUP.md               ← 部署指南
│   └── VERIFICATION.md        ← 验证清单
├── testing/
│   └── TESTING.md             ← 测试文档
└── PROGRESS.md                ← 开发进度总表
```

## 触发时机

本 skill 在以下场景**自动触发**：
1. Agent 完成代码修改并通过 code-review 后
2. Agent 执行 git commit 前
3. 用户显式要求"检查文档"或"同步文档"时

## 常见陷阱

- 仅检查文件是否存在，不检查函数签名/参数是否一致 — 导致文档内容过期
- 更新文档时破坏原有格式和结构 — 应保持文档风格一致
- 遗漏 PROGRESS.md 和 README.md 的索引更新 — 这两个文件是项目门面
- 对 v2.0_improve.md 等规划文档进行"同步" — 规划文档描述的是未来目标，不应与当前代码"对齐"
