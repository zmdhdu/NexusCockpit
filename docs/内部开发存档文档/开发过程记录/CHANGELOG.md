# NexusCockpit 变更日志

所有版本变更记录遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

---

## [2.3.0] — 2026-08-03

### 新增
- **多需求并行调度架构**: VehicleExpert 支持单条指令内多动作并行执行
  - 遍历全部 intent 字段收集匹配动作，`asyncio.gather` 并行执行
  - 互斥组（`_MUTEX_GROUPS`）内串行执行，避免硬件冲突
  - `_execute_single` 异常兜底：`asyncio.wait_for(timeout=10s)` 捕获通信超时
- **路由防漂移机制**: Supervisor `_determine_experts` 增加路由错配检测
  - 车控指令强制路由到 vehicle 专家（优先级最高）
  - Navigation_Action 无 destination 且与车控意图共现时判定为误匹配
  - 路由错配自动修复：强制添加 vehicle 专家并记录 CRITICAL 日志
- **Sandbox 参数强校验拦截器**: 操作符枚举校验 + 类型校验 + 空值拦截
  - climate/window/seat/media 全部增加合法操作符枚举（`_VALID_OPS`）
  - 非法操作符直接阻断执行并返回标准化错误提示
  - 参数类型错误从静默忽略升级为阻断执行
- **Heuristic Router 文本分段解析**: `_split_segments` 按标点拆解复合指令
  - 各 extractor 仅在包含领域关键词的子句内解析操作动词
  - 彻底解决"打开音乐，关闭车窗"跨域关键词误匹配问题
- **Dispatch Node 多专家聚合优化**: `tool_results` 列表收集 + `multi_actions` 追踪
  - 并行调度全流程日志埋点（专家详情、多动作数量）
- **Responder B3 分支增强**: 多专家回复分组聚合 + 空回复兜底

### 修复
- **空调控制链路**: `climate_state.py` power_on/power_off 不再提前 return，
  后续温度/风量/模式参数正常生效
- **多需求并行失效**: `vehicle_expert.py` 废弃「首个匹配即 return」逻辑，
  改为遍历全部 intent 字段收集所有匹配动作
- **跨域关键词误匹配**: `heuristic.py` `_extract_window` 等方法改为分段解析，
  操作动词仅在领域子句内生效
- **车窗操作符缺失**: `window_state.py` 未显式匹配 `open`/`up`/`raise`，
  未知 op 默认 100%（全开），现增加操作符枚举校验
- **座椅非法位置**: `seat_state.py` 未知 position 覆盖 driver 状态，
  现增加位置枚举校验，非法 position 回退到 driver
- **媒体未知操作**: `media_state.py` 未知 op 静默返回成功，
  现增加操作符枚举校验
- **冗余导入**: `vehicle_expert.py` `_verify_result` 内部重复导入 `SkillResult`

### 优化
- 全部 mock state 文件统一增加 `_VALID_OPS` / `_VALID_POSITIONS` 枚举校验
- `window_state.py` 单独车窗操作后同步 `all` 字段为最大值
- `seat_state.py` 座椅档位增加上界限制 `min(3, ...)`
- `climate_state.py` 参数设置后构建完整回复消息（电源+温度+风量+模式）

---

## [2.2.0] — 2026-08-01

### 新增
- **智能上下文记忆管理**: 阈值压缩 + 滚动摘要 + 上下文 token 预算控制
  - `MEMORY_COMPRESS_THRESHOLD_TURNS` / `MEMORY_KEEP_RECENT_TURNS` 等配置项
- **本地 LLM 降级**: 云端 DeepSeek-V3 → 本地 Qwen3.5-4B (llama.cpp) 自动降级
  - `LLM_FALLBACK_ENABLED` 一键开关，`LLAMA_CPP_SUBPROCESS` 子进程管理
- **渐进式反思校验**: 对所有非工具类回复做 LLM 质量校验 + retry
- **搜索类回复反思**: 检查回复是否基于搜索结果，防止时效性/日期错误
- **确定性日期校验**: 正则表达式检测日期错误，无需 LLM 调用
- **座舱主题色配置化**: `COCKPIT_THEMES` / `COCKPIT_NAMES` 环境变量
- **Prometheus 查询接入**: Go 网关 dataplatform 并发/QPS 实时指标
- **NodeContext 桥接**: SupervisorGraph 上帝类拆分基础设施就绪

### 优化
- **chat.py 重复逻辑提取**: 缓存查询/会话历史/缓存写入等 5 处公共函数
- **Go handlers TCP 检查循环化**: `GetAllMiddlewareStatus` 从重复代码重构为循环
- **SSE 心跳保活**: 按配置间隔发送 SSE 注释行，防止代理超时断连
- **会话并发锁**: 防止同一 session 的并发请求交叉污染历史

### 修复
- Neo4j/Redis/MySQL/Prometheus 默认端口一致性修复
- JWT 双端默认密钥统一为 `nexus-cockpit-secret`
- checkpoint 路径从 `os.getcwd()` 改为 `config.project_root`
- pyproject.toml 版本和依赖与 requirements.txt 对齐
- 车控指令缓存隔离: `has_side_effect` 二次安全防护
- 硬编码路径修复: Go 日志/Python checkpoint/座舱主题色

### 移除
- `RabbitMQConfig` 和 `OSSConfig` 废弃配置注释
- `requirements_no_torch.txt` (合并到 requirements.txt)
- `create_tool_node()` / `build_graph_with_reflection_loop()` / `build_graph_with_parallel_experts()` 未使用函数
- `SPLIT_PUNCT` 无效常量别名

---

## [2.1.0] — 2026-07-15

### 新增
- **多座舱架构**: 座舱级数据隔离 (Redis DB / 用户 / 主题色)
- **Go 网关 (NexusGate)**: Gin + JWT 鉴权 + 优先级限流 + WebSocket Hub
- **RBAC 权限**: admin / cockpit_user 双角色
- **声纹识别**: CAM++ 模型，`VOICEPRINT_THRESHOLD` 可配置
- **数据中台**: 跨座舱统计看板，Go 原生查 Redis

### 优化
- 环境变量分层加载: `.env.local` / `.env.prod` / `.env` 自动切换
- 生产环境安全检查: 默认弱密钥/弱口令/CORS 通配符拒绝启动
- 数据保留策略管理: 后台自动清理过期日志

---

## [2.0.0] — 2026-06-01

### 新增
- **Multi-Agent 架构**: LangGraph Supervisor + 5 Expert Agents + Responder + Reflection + Reviewer
- **GraphRAG 三路融合**: Milvus (向量) + Neo4j (图谱) + BM25 (全文) RRF 融合 + Rerank 重排
- **语义缓存**: Redis 8 RediSearch KNN 向量缓存
- **语音交互**: ASR (SenseVoice) + TTS (CosyVoice) + 声纹识别 (CAM++)
- **可观测性**: Langfuse Tracing + Prometheus Metrics + Grafana 可视化
- **FastAPI REST + SSE + WebSocket** 全栈 API
- **Docker 全栈本地部署**: Milvus/Neo4j/Redis/MySQL/Langfuse
