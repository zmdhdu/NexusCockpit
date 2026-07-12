# 变更影响评估报告

## 变更概要
- **变更时间**: 2026-07-12
- **变更类型**: Bug 修复 + 新增功能 + 重构 + 配置变更
- **影响等级**: Major
- **变更基线**: commit `2dfe810` (feat: v2.1设计文档 + 搜索增强 + 前端车控UI重构 + LLM供应商切换)
- **变更范围**: 44 个已跟踪文件修改 (+3461 / -720 行)，27 个新增文件

---

## 改动文件清单

### 后端 — Python

| 文件路径 | 变更类型 | 改动行数 | 风险等级 | 说明 |
|----------|----------|----------|----------|------|
| `backend_design/nexus/config.py` | 修改 | +33 | Medium | 新增 `CockpitSettings` 多座舱配置类，挂载到 `AppConfig.cockpit` |
| `backend_design/nexus/api/routes/auth.py` | 修改 | +32 | High | 登录接口注入 `role`/`cockpit_id` claims；新增修改密码端点 |
| `backend_design/nexus/api/routes/chat.py` | 修改 | +97 | High | 新增座舱级指标记录 + 聊天日志持久化逻辑（Redis + MySQL） |
| `backend_design/nexus/api/routes/vehicle.py` | 修改 | +34 | Medium | 新增车辆控制 API 端点 |
| `backend_design/nexus/vehicle/mock.py` | 修改 | +118 | High | 新增 GPS 逆地理编码 + IP 定位降级策略；空调电源开关逻辑；位置查询 |
| `backend_design/nexus/agent/supervisor_graph.py` | 修改 | +187 | High | Supervisor 工作流集成多座舱路由 + MainAgent 确认层 |
| `backend_design/nexus/agent/responder.py` | 修改 | +64 | Medium | 响应器适配多座舱上下文 |
| `backend_design/nexus/main.py` | 修改 | +125 | High | 应用启动流程集成 DB 连接池、座舱管理器、SubAgent 巡检 |
| `backend_design/nexus/memory/manager.py` | 修改 | +268 | High | 记忆管理器重构为按座舱隔离存储 |
| `backend_design/nexus/memory/compressor.py` | 修改 | +115 | Medium | 记忆压缩器适配多座舱场景 |
| `backend_design/nexus/memory/__init__.py` | 修改 | +20 | Low | 模块导出更新 |
| `backend_design/nexus/models/state.py` | 修改 | +4 | Low | State 模型新增 `cockpit_id` 字段 |
| `backend_design/nexus/intent/heuristic.py` | 修改 | +14 | Medium | 启发式意图识别新增位置查询关键词 |
| `backend_design/nexus/intent/router.py` | 修改 | +3 | Low | 意图路由适配 |
| `backend_design/nexus/skills/vehicle/navigation.py` | 修改 | +8 | Low | 导航技能适配新参数 |
| `backend_design/nexus/skills/vehicle/status.py` | 修改 | +12 | Low | 状态技能适配位置查询 |
| `backend_design/nexus/vehicle/factory.py` | 修改 | +21 | Medium | 车辆适配器工厂支持多座舱实例 |
| `backend_design/nexus/rag/cherry_kb.py` | 修改 | +4 | Low | RAG 检索适配 |
| `backend_design/nexus/api/routes/health.py` | 修改 | +4 | Low | 健康检查微调 |
| `backend_design/nexus/prompts/chat.md` | 修改 | +22 | Low | 对话 Prompt 模板更新 |

### 后端 — 新增文件

| 文件路径 | 变更类型 | 风险等级 | 说明 |
|----------|----------|----------|------|
| `backend_design/nexus/api/routes/middleware_status.py` | 新增 | Medium | 中间件状态看板 API（Redis/Milvus/Neo4j/RabbitMQ/MySQL） |
| `backend_design/nexus/api/routes/cockpit.py` | 新增 | Medium | 座舱管理 API（增删查改 + 切换） |
| `backend_design/nexus/api/routes/dataplatform.py` | 新增 | Low | 数据平台 API |
| `backend_design/nexus/api/routes/settings.py` | 新增 | Medium | 系统设置 API（用户偏好持久化） |
| `backend_design/nexus/agent/mainagent_confirm.py` | 新增 | High | MainAgent 确认层（高风险操作二次确认） |
| `backend_design/nexus/agent/subagent_monitor.py` | 新增 | High | SubAgent 巡检监控（三层降本异常检测） |
| `backend_design/nexus/core/cockpit_manager.py` | 新增 | High | 座舱管理器（多座舱生命周期管理） |
| `backend_design/nexus/core/db_manager.py` | 新增 | High | MySQL 数据库管理器（连接池 + CRUD） |
| `backend_design/nexus/core/tenant_context.py` | 新增 | Medium | 多租户上下文（座舱 ID 传递中间件） |
| `backend_design/nexus/core/voiceprint.py` | 新增 | Medium | 声纹识别模块 |
| `backend_design/nexus/models/cockpit.py` | 新增 | Medium | 座舱数据模型（Pydantic） |
| `backend_design/nexus/observability/cockpit_metrics.py` | 新增 | Medium | 座舱级 Prometheus 指标采集 |
| `backend_design/nexus/observability/data_retention.py` | 新增 | Low | 数据保留策略（自动清理过期数据） |
| `backend_design/scripts/gen_music.py` | 新增 | Low | 真实音乐生成脚本（多轨谐波合成） |
| `backend_design/scripts/v2.1_migration.sql` | 新增 | High | v2.1 数据库迁移脚本 |
| `backend_design/scripts/chaos_test.py` | 新增 | Low | 混沌测试脚本 |
| `backend_design/scripts/test_api.py` | 新增 | Low | API 集成测试 |
| `backend_design/scripts/test_db.py` | 新增 | Low | 数据库测试 |
| `backend_design/scripts/test_metrics.py` | 新增 | Low | 指标采集测试 |
| `backend_design/tests/test_v21.py` | 新增 | Medium | v2.1 功能测试 |
| `backend_design/Dockerfile` | 新增 | Medium | 后端容器化构建文件 |

### 前端 — TypeScript/TSX

| 文件路径 | 变更类型 | 改动行数 | 风险等级 | 说明 |
|----------|----------|----------|----------|------|
| `frontend_design/src/stores/chat-store.ts` | 修改 | +135 -75 | High | 对话历史重构为按座舱 ID 分组持久化 |
| `frontend_design/src/components/chat/chat-window.tsx` | 修改 | +81 | High | 集成语音输入 + TTS 朗读 + 车控事件刷新 |
| `frontend_design/src/lib/api.ts` | 修改 | +283 | High | API 客户端新增座舱管理/数据平台/中间件/设置等接口 |
| `frontend_design/src/types/index.ts` | 修改 | +125 | Medium | 类型定义新增座舱/数据平台/管理员等接口 |
| `frontend_design/src/components/layout/sidebar.tsx` | 修改 | +196 | Medium | 侧边栏新增多座舱切换 + 管理员入口 |
| `frontend_design/src/app/dashboard/page.tsx` | 修改 | +539 | Medium | 仪表盘重构为多座舱视图 |
| `frontend_design/src/app/settings/page.tsx` | 修改 | +608 | Medium | 设置页新增 LLM 供应商/语音/隐私等配置 |
| `frontend_design/src/app/vehicle/page.tsx` | 修改 | +19 | Low | 车控页适配 |
| `frontend_design/src/components/vehicle/vehicle-panel.tsx` | 修改 | +73 | Medium | 车控面板适配位置查询和空调电源 |
| `frontend_design/src/components/vehicle/voice-assistant-bar.tsx` | 修改 | +26 | Low | 语音助手条适配 |
| `frontend_design/src/app/page.tsx` | 修改 | +8 | Low | 首页微调 |
| `frontend_design/next.config.js` | 修改 | +6 | Low | Next.js 配置更新 |

### 前端 — 新增文件

| 文件路径 | 变更类型 | 风险等级 | 说明 |
|----------|----------|----------|------|
| `frontend_design/src/app/admin/page.tsx` | 新增 | Medium | 管理员看板（中间件状态 + 活动时间线 + SubAgent 告警） |
| `frontend_design/src/app/cockpit/page.tsx` | 新增 | Medium | 座舱管理页 |
| `frontend_design/src/app/dataplatform/page.tsx` | 新增 | Low | 数据平台页 |
| `frontend_design/src/app/middleware/page.tsx` | 新增 | Low | 中间件监控页 |
| `frontend_design/src/lib/tts.ts` | 新增 | Medium | 浏览器 TTS 语音合成封装 |
| `frontend_design/src/lib/vehicle-events.ts` | 新增 | Low | 车控事件总线（跨组件通信） |
| `frontend_design/src/stores/auth-store.ts` | 新增 | High | 认证状态管理（JWT Token + 座舱 ID + 角色） |
| `frontend_design/Dockerfile` | 新增 | Medium | 前端容器化构建文件 |

### 配置 & 文档

| 文件路径 | 变更类型 | 风险等级 | 说明 |
|----------|----------|----------|------|
| `.env` / `.env.example` | 修改 | Medium | 新增多座舱/DB/声纹等环境变量 |
| `docker-compose.yml` | 修改 | Medium | 新增 NexusGate(Go网关) + Grafana + Loki 等服务 |
| `config/prometheus/prometheus.yml` | 修改 | Low | Prometheus 采集目标更新 |
| `docs/v2.1-design.md` | 修改 | Low | v2.1 设计文档补充 |
| `docs/PROGRESS.md` | 修改 | Low | 开发进度更新 |
| `docs/doc_sync_report.md` | 修改 | Low | 文档同步报告 |

---

## 影响范围分析

### 直接受影响模块

1. **`nexus.config` — 全局配置系统**
   - 新增 `CockpitSettings` 配置类，挂载到 `AppConfig.cockpit`
   - 所有通过 `get_config()` 访问配置的模块自动获得新配置项
   - **验证点**: 确保 `.env` 中新增的环境变量被正确加载

2. **`nexus.api.routes.chat` — 对话 API**
   - 新增 `_record_chat_metrics()` 函数，在每次对话后写入 Redis 指标 + MySQL 日志
   - 新增 `cockpit_id` 注入到 Agent State
   - **验证点**: 确保 Redis/MySQL 不可用时对话不中断（已有 try/except 降级）

3. **`nexus.vehicle.mock` — 车辆模拟器**
   - `vehicle_navigation()` 签名变更：新增 `op`/`latitude`/`longitude` 参数
   - 新增 `_fetch_ip_location()` 方法（调用外部 HTTP 接口）
   - `vehicle_status()` 签名变更：新增 `op` 参数
   - **验证点**: 所有调用 `vehicle_navigation()` 和 `vehicle_status()` 的上游需适配新参数

4. **`nexus.api.routes.auth` — 认证路由**
   - `login()` 新增 `extra_claims` 注入 `role` 和 `cockpit_id`
   - 新增 `/change-password` 端点
   - **验证点**: JWT Token 解析端需支持新 claims

5. **`frontend_design chat-store.ts` — 对话状态管理**
   - 数据结构从 `messages: Message[]` 变更为 `messagesByCockpit: Record<string, Message[]>`
   - `persist` 的 `partialize` 和 `onRehydrateStorage` 逻辑重写
   - **验证点**: 旧的 localStorage 数据（`nexus-chat-store` key）格式不兼容，需清理或迁移

6. **`frontend_design chat-window.tsx` — 对话窗口组件**
   - 新增 Web Speech API 语音输入 + TTS 朗读
   - 新增 `useAuth` 座舱 ID 同步
   - **验证点**: 浏览器不支持 Speech API 时的降级表现

### 间接受影响模块

1. **`nexus.agent.supervisor_graph` — Supervisor 工作流**
   - 通过 `state["cockpit_id"]` 获取座舱上下文
   - MainAgent 确认层在车控等高风险操作时介入
   - **验证点**: 确认层不阻塞正常对话流程

2. **`nexus.memory.manager` — 记忆管理器**
   - 记忆按座舱 ID 隔离存储
   - **验证点**: 座舱切换后记忆不串扰

3. **`nexus.intent.heuristic` — 启发式意图识别**
   - 新增"位置"/"我在哪"等关键词路由
   - **验证点**: 不影响现有意图识别准确率

4. **`frontend_design sidebar.tsx` — 侧边栏导航**
   - 新增座舱切换组件，触发 `auth-store` 更新
   - **验证点**: 座舱切换后 `chat-store` 正确加载历史

5. **`frontend_design vehicle-panel.tsx` — 车控面板**
   - 监听 `vehicle-events` 刷新事件
   - **验证点**: 事件未触发时面板不空转

---

## 风险评估矩阵

| # | 风险项 | 严重程度 | 发生概率 | 风险等级 | 缓解措施 |
|---|--------|----------|----------|----------|----------|
| R1 | `vehicle_navigation()` 签名变更导致上游调用 TypeError | High | Medium | **High** | 新增参数均有默认值，旧调用方式向后兼容 |
| R2 | 前端 localStorage 旧格式数据导致 `onRehydrateStorage` 崩溃 | Medium | High | **High** | `onRehydrateStorage` 已加 `?.` 可选链防护；建议首次加载清理旧 key |
| R3 | MySQL 连接池初始化失败导致服务启动崩溃 | High | Low | **Medium** | `db_manager.connect()` 有 try/except，`is_connected` 标志位降级 |
| R4 | 外部 HTTP 接口（Nominatim/ip-api）不可达导致定位超时 | Medium | Medium | **Medium** | 5s 超时 + 三级降级策略（GPS → IP → 默认值） |
| R5 | JWT 新增 claims 导致旧 Token 解析异常 | Medium | Low | **Low** | `extra_claims` 是可选字段，旧 Token 不含也不报错 |
| R6 | SubAgent 巡检在空闲座舱误报缓存命中率异常 | Medium | Medium | **Medium** | 已新增 `min_sample_count=10` 阈值，样本不足时跳过检查 |
| R7 | MainAgent 确认层阻塞正常对话 | High | Low | **Medium** | 确认层仅对 `has_side_effect=True` 的操作介入 |
| R8 | Redis 不可用时座舱指标记录失败影响对话 | Low | Low | **Low** | `_record_chat_metrics` 有 try/except 降级，仅记录日志 |
| R9 | Web Speech API 在非 HTTPS 环境不可用 | Medium | Medium | **Medium** | `useSpeechRecognition` 返回 `supported=false`，UI 禁用麦克风按钮 |
| R10 | docker-compose 新增服务（NexusGate/Grafana/Loki）端口冲突 | Low | Medium | **Low** | 默认端口已避开常用端口，可通过 `.env` 配置 |

---

## 回归测试建议

### 1. 必测项（P0 — 阻塞发布）

- [ ] **对话流程端到端**: 发送文本消息 → 流式返回 → 车控触发 → 面板刷新 → TTS 朗读
- [ ] **多座舱对话隔离**: 在座舱 A 对话 → 切换到座舱 B → 座舱 A 历史保留 → 切回座舱 A 历史恢复
- [ ] **位置查询**: 发送"我在哪" → 返回 GPS/IP 定位地址（验证 Nominatim 逆地理编码）
- [ ] **空调电源控制**: "打开空调" / "关闭空调" → 车控面板状态更新
- [ ] **认证流程**: 登录获取 Token → 携带 Token 访问受保护接口 → Token 过期处理
- [ ] **中间件状态**: 管理员页面访问 `/api/middleware/` → Redis/MySQL 状态正确返回
- [ ] **SubAgent 巡检**: 空闲座舱不误报 → 活跃座舱正常采集指标

### 2. 建议测试（P1 — 发布前完成）

- [ ] **语音输入**: 点击麦克风 → 说话 → 识别结果填入输入框 → 自动发送
- [ ] **TTS 朗读**: 对话回复后自动语音合成播放
- [ ] **页面刷新恢复**: 对话中途刷新页面 → 历史消息从 localStorage 恢复
- [ ] **管理员活动时间线**: 查看告警列表 → JSON 正确渲染为可读摘要
- [ ] **数据库迁移**: 执行 `v2.1_migration.sql` → 表结构正确创建
- [ ] **Docker 容器化**: `docker-compose up` → 所有服务正常启动
- [ ] **声纹识别**: 注册声纹 → 1:N 匹配 → 阈值过滤

### 3. 性能基准（P2 — 持续监控）

- [ ] ASR → LLM 首句延迟 < 3s
- [ ] 流式对话首 token 延迟 < 2s
- [ ] 座舱切换对话恢复延迟 < 100ms（localStorage 读取）
- [ ] 位置查询（含 HTTP 调用）延迟 < 6s（5s 超时 + 1s 处理）
- [ ] SubAgent 巡检不阻塞主请求路径（异步后台执行）
- [ ] MySQL 连接池在 50 并发下无连接泄漏

---

## 回滚方案

1. **Git 回滚**:
   ```bash
   git stash  # 暂存当前未提交的修改
   git checkout 2dfe810  # 回退到变更前 commit
   ```

2. **数据库回滚**:
   ```sql
   -- 回滚 v2.1 迁移（删除新增表）
   DROP TABLE IF EXISTS chat_logs;
   DROP TABLE IF EXISTS subagent_logs;
   DROP TABLE IF EXISTS mainagent_confirm_logs;
   DROP TABLE IF EXISTS user_habits;
   DROP TABLE IF EXISTS cockpits;
   ```

3. **前端 localStorage 清理**:
   ```javascript
   // 浏览器控制台执行
   localStorage.removeItem('nexus-chat-store');
   localStorage.removeItem('nexus-auth-store');
   ```

4. **Docker 服务回滚**:
   ```bash
   docker-compose down  # 停止所有 v2.1 新增服务
   # 恢复旧版 docker-compose.yml 后重新启动
   ```

---

## 附录：本次会话修复问题追踪

| # | 问题 | 根因 | 修复方案 | 验证状态 |
|---|------|------|----------|----------|
| 1 | `ASRConfig` 属性错误 | 引用了不存在的 `resolved_sensevoice_path` | 更正为 `resolved_funasr_path` | ✅ 已修复 |
| 2 | `UserResponse` 数据验证失败 | `cockpit_id` 为 `None` 时 Pydantic 校验崩溃 | 字段设为可选默认空字符串 | ✅ 已修复 |
| 3 | 管理员中间件状态获取失败 | API 路由配置方法调用错误 | 修正 `middleware_status.py` 路由注册 | ✅ 已修复 |
| 4 | 音乐播放为模拟正弦波 | 缺少真实音频文件 | 编写 `gen_music.py` 生成 10 首多轨立体声 WAV | ✅ 已修复 |
| 5 | 缺少语音输入支持 | 前端未集成 Web Speech API | `chat-window.tsx` 集成 `useSpeechRecognition` Hook | ✅ 已修复 |
| 6 | 定位不准确 | 仅使用硬编码默认位置 | GPS 逆地理编码 + IP 定位 + 默认值三级降级 | ✅ 已修复 |
| 7 | 活动时间线 JSON 渲染错误 | 前端直接渲染原始 JSON 字符串 | 解析为可读摘要 + 时间线组件 | ✅ 已修复 |
| 8 | 切换座舱对话记录消失 | 消息存储为单一数组，切换时被覆盖 | 重构为 `messagesByCockpit` 按座舱 ID 分组 | ✅ 已修复 |
| 9 | 空闲座舱 SubAgent 误报 | 缓存命中率检查无最小样本数阈值 | 新增 `min_sample_count=10` 过滤 | ✅ 已修复 |
| 10 | `CockpitSettings` 缺少 `cockpits` 属性导致中间件状态接口 500 | `middleware_status.py` 旧代码引用了 `get_config().cockpit.cockpits`，但 `CockpitSettings` 无此字段 | 改为 `config.cockpit.default_cockpit_count`（config.py 第 564 行定义的合法属性） | ✅ 已修复 |
| 11 | 服务关闭时 `RuntimeWarning: coroutine 'Connection.close' was never awaited` | `main.py` 第 316 行调用 `AsyncSqliteSaver` 的 `aiosqlite.Connection.close()` 未加 `await`，该方法是协程 | 改为 `await app.state.checkpoint_saver.conn.close()`，并补充异常日志 | ✅ 已修复 |
