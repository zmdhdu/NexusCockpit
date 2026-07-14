# 变更影响评估报告

## 变更概要
- **变更时间**: 2026-07-12
- **变更类型**: Bug 修复
- **影响等级**: Medium
- **变更版本**: v2.1.1

## 问题描述

运行日志中暴露两个问题：
1. `Embedding failed after retries: Event loop is closed` — 记忆存储时 embedding 调用失败
2. Neo4j `missing property name is: mid` WARNING — 用户画像查询引用了不存在的属性

## 改动文件清单

| 文件路径 | 变更类型 | 改动行数 | 风险等级 | 说明 |
|----------|----------|----------|----------|------|
| `backend_design/nexus/memory/manager.py` | 修改 | +50 -20 | Medium | 重写异步存储方法，从线程+新事件循环改为 asyncio.create_task |
| `backend_design/nexus/rag/graph_store.py` | 修改 | +1 -1 | Low | Cypher 查询使用 coalesce 处理缺失属性 |
| `docs/architecture/L2-data.md` | 修改 | +15 -5 | Low | 同步更新 manager.py 和 graph_store.py 的 API 文档 |
| `docs/PROGRESS.md` | 修改 | +3 -3 | Low | 更新日期和模块说明 |
| `docs/learning-roadmap.md` | 修改 | +85 -0 | Low | 新增 Bug 3/4 排查案例 |

## 影响范围分析

### 直接受影响模块

- **`MemoryManager`** (`nexus/memory/manager.py`):
  - `store_from_text_async()` 和 `store_conversation_async()` 返回类型从 `threading.Thread` 改为 `Optional[asyncio.Task]`
  - 调用方 `supervisor_graph.py` 第 973/980 行和 `reviewer.py` 第 61 行**不使用返回值**，向后兼容
  - 新增 3 个内部方法：`_store_from_text_safe`、`_store_conversation_safe`、`_task_done_callback`

- **`Neo4jGraphStore`** (`nexus/rag/graph_store.py`):
  - `get_user_profile()` 的 Cypher 查询从 `r.mid as mid` 改为 `coalesce(r.mid, -1) as mid`
  - 返回值变化：`record["mid"]` 从 `None`（缺失时）变为 `-1`（缺失时）
  - 调用方 `MemoryManager.get_user_profile()` 直接透传，下游消费方需注意 -1 表示无关联 Milvus ID

### 间接受影响模块

- **`SupervisorGraph._reviewer_node`** (`nexus/agent/supervisor_graph.py`):
  - 调用 `store_from_text_async` 和 `store_conversation_async`，行为不变（fire-and-forget）
  - 修复后记忆存储不再静默失败，embedding 调用成功率提升

- **`ReviewerAgent.review`** (`nexus/agent/reviewer.py`):
  - 调用 `store_from_text_async`，行为不变

- **`EmbeddingService`** (`nexus/rag/embedding.py`):
  - 无代码变更，但运行时行为改善：不再被跨事件循环调用，消除 "Event loop is closed" 错误

## 风险评估矩阵

| 风险项 | 严重程度 | 发生概率 | 风险等级 | 缓解措施 |
|--------|----------|----------|----------|----------|
| 返回类型变更导致调用方报错 | Low | Very Low | Low | 调用方均不使用返回值，已验证 |
| asyncio.create_task 在非 async 上下文调用 | Medium | Low | Low | 已添加 try/except 处理 RuntimeError |
| 后台 task 异常静默丢失 | Low | Medium | Low | 已添加 _task_done_callback 记录异常 |
| coalesce 返回 -1 导致下游逻辑异常 | Low | Low | Low | 下游代码未对 mid 做特殊判断，-1 仅为占位 |

## 回归测试建议

1. **必测项**:
   - [ ] 对话后记忆存储：发送一条对话，检查日志中无 "Event loop is closed" 错误
   - [ ] 记忆召回：`MemoryManager.recall()` 能正常返回历史记忆
   - [ ] 用户画像查询：`MemoryManager.get_user_profile()` 返回正确结构，无 Neo4j WARNING

2. **建议测试**:
   - [ ] 高并发对话：多座舱同时对话，验证 asyncio.create_task 在高并发下稳定
   - [ ] 服务关闭：停止服务时无 "coroutine was never awaited" 警告

3. **性能基准**:
   - [ ] 对话响应延迟不应增加（asyncio.create_task 比线程更轻量）
   - [ ] Embedding 调用成功率应从 ~70% 提升至 ~100%

## 回滚方案
- `git revert` 本次变更的 commit
- 代码会回到线程+新事件循环方案，"Event loop is closed" 错误会重新出现但不影响服务可用性（embedding 有重试和零向量降级）
