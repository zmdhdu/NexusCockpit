# NexusCockpit 项目踩坑备忘录

> **用途**: 后续开启全新会话让 AI 修改代码时，直接参考本文件，避免重复踩历史坑。
> **更新日期**: 2026-08-03

---

## 一、历史重大底层问题清单 + 最终根因与解决方案

### 1.1 路由漂移问题

| 问题 | 根因 | 解决方案 | 涉及文件 |
|------|------|----------|----------|
| 天气路由错误 | 启发式路由关键词匹配过宽 | 精确化关键词白名单，新增 Weather_Action 独立意图字段 | intent/heuristic.py, intent/constants.py |
| 空调指令路由漂移至导航 | 车控指令被导航路由误匹配 | 车控意图特征白名单强制路由到 vehicle 专家，检测 Navigation_Action 误匹配并自动重路由 | agent/nodes/supervisor_node.py |


**排查方式**: 在 supervisor_node.py 的 _determine_experts() 方法中搜索 Route drift detected 日志关键字。

### 1.2 对话存储问题

| 问题 | 根因 | 解决方案 | 涉及文件 |
|------|------|----------|----------|
| 对话存储仅保存用户消息 | store_conversation_async 未调用 final_response | Reviewer 节点同步执行记忆存储，传入 user_input + final_response 双向持久化 | agent/nodes/reviewer_node.py, memory/manager.py |

**排查方式**: 在 reviewer_node.py 中搜索 conversation_vectorized 日志关键字。

### 1.3 并行调度失效问题

| 问题 | 根因 | 解决方案 | 涉及文件 |
|------|------|----------|----------|
| 单条复合需求只能执行单一任务 | 旧架构线性执行 | 改为 asyncio.gather 并行调用所有活跃专家 | agent/nodes/dispatch_node.py |
| 多动作车控只能执行首个动作 | VehicleExpert 只执行单个 intent_key | VehicleExpert 多动作并行执行：收集匹配 -> 互斥组串行 -> asyncio.gather -> 结果聚合 | agent/experts/vehicle_expert.py |

**排查方式**: 在 dispatch_node.py 中搜索 Dispatch done 日志关键字。

### 1.4 界面切换强制终止 LLM 生成问题

| 问题 | 根因 | 解决方案 | 涉及文件 |
|------|------|----------|----------|
| 界面切换强制终止 LLM 生成 | 前端路由切换时直接中断 SSE 流 | AI 流式生成任务生命周期隔离方案：前端切换页面时不中断后端任务 | agent/supervisor_graph.py, agent/generation_task_pool.py |

**排查方式**: 在 supervisor_graph.py 的 stream_with_events() 方法中查看任务生命周期管理逻辑。

### 1.5 车控指令参数问题

| 问题 | 根因 | 解决方案 | 涉及文件 |
|------|------|----------|----------|
| 车窗仅支持全开全关 | Window mock state 只实现了 open/close | 新增 set_percent 操作符，支持单窗/多窗组合控制，百分比开度 | vehicle/mock/window_state.py, skills/vehicle/window.py |
| 空调空参数、非法参数下发异常 | Sandbox inspect() 仅警告不阻断 | 参数校验从仅警告升级为阻断执行，增加操作符枚举校验 | core/sandbox.py, vehicle/mock/climate_state.py |
| 全部 mock state 缺少操作符校验 | mock state 直接接受任意 op | climate/window/seat/media 全部增加操作符枚举校验 | vehicle/mock/*.py |

**排查方式**: 在 mock state 文件中搜索 Invalid op 错误消息。

### 1.6 代码注释冗余问题

| 问题 | 根因 | 解决方案 | 涉及文件 |
|------|------|----------|----------|
| 大量冗长流程型注释 | 历史迭代中注释不断堆积 | 统一简化规范：删除冗余注释，保留关键设计决策注释 | 全项目源码 |
| 版本号/阶段标记散落注释中 | 历史迭代标记 P0-x/P1-x/P2-x 未清理 | 全文清理所有版本号和阶段标记 | 全项目源码 |

---

## 二、项目改造红线约束

1. **禁止依靠增加 Prompt 修复 BUG**: 所有异常优先底层代码整改，不允许通过修改 Prompt 文本来掩盖程序缺陷
2. **不修改业务代码逻辑**: 文档更新和注释清理仅修改文字描述，不改动代码执行逻辑
3. **全文禁止版本号**: 所有 md 文档、代码注释、配置说明中不出现任何版本号信息
4. **文档与代码 100% 对齐**: 文档描述必须与当前整改完成后的源码逻辑完全一致

---

## 三、模块取舍标准

### 降级/裁撤策略

| 模块 | 处理方式 | 原因 |
|------|----------|------|
| middleware/task_queue.py | 已删除 | asyncio.create_task 封装多余，改为 reviewer_node.py 直接 await |
| agent/nodes/conflict_detector.py | 已删除 | 未在工作流中使用，ConflictDetector 已在 memory/conflict.py 实现 |
| memory/context_coordinator.py | 已删除 | 上下文管理已拆分到 supervisor_node.py 和 responder_node.py |
| Celery/RabbitMQ | 已移除 | 改为 asyncio 进程内异步执行，降低部署复杂度 |
| BERT 路由 | 已移除 | 始终为 None，从未实现 |
| SubAgent 监控器 | 已移除 | 过度设计 |
| MainAgent 确认层 | 已移除 | 过度设计 |

### 取舍原则

- **低收益模块**: 降级或裁撤（如 BERT 路由从未实现，直接移除）
- **负干扰模块**: 立即删除（如 task_queue 封装多余且增加维护成本）
- **笨重模块**: 精简瘦身（如 SupervisorGraph 从 ~800 行瘦身为 ~280 行，节点逻辑拆分到 nodes/ 目录）

---

## 四、代码注释统一标准

1. **模块级注释**: 文件头部 docstring 描述模块职责、核心功能、架构位置
2. **类级注释**: 描述类职责、依赖注入方式、关键参数
3. **方法级注释**: 描述方法作用、使用场景、参数含义、返回值
4. **行内注释**: 仅对复杂逻辑、非直观设计决策添加行内注释
5. **禁止**: 版本号、阶段标记（P0/P1/P2）、临时调试说明、过时设计思路描述

---

## 五、常见调试日志关键字与排查方式

### 路由排查

| 日志关键字 | 文件 | 含义 |
|------------|------|------|
| Route drift detected | supervisor_node.py | 车控指令被误匹配为导航，自动重路由 |
| CRITICAL route mismatch | supervisor_node.py | 车控意图未路由到 vehicle 专家，自动修复 |
| Fast-path: heuristic vehicle command | supervisor_node.py | 纯车控指令走快速路径 |
| Mixed-intent | supervisor_node.py | 混合意图检测，车控+非车控并行 |
| Compound query routed | supervisor_node.py | 复合查询检测，走完整 LLM 路由 |

### 并行调度排查

| 日志关键字 | 文件 | 含义 |
|------------|------|------|
| Dispatch done | dispatch_node.py | 专家并行执行完成 |
| Expert raised | dispatch_node.py | 专家执行异常 |

### 输出校验排查

| 日志关键字 | 文件 | 含义 |
|------------|------|------|
| Output gateway PASSED | output_gateway.py | 全局输出校验通过 |
| Output gateway: empty | output_gateway.py | 输出为空，使用兜底话术 |
| Output gateway: sensitive | output_gateway.py | 检测到敏感内容，拦截 |
| Output gateway: hallucinated | output_gateway.py | 检测到编造对话历史，拦截 |
| Output gateway: too long | output_gateway.py | 输出过长，截断 |

### 记忆存储排查

| 日志关键字 | 文件 | 含义 |
|------------|------|------|
| conversation_vectorized | reviewer_node.py | 对话已向量化存储 |
| memory_storage_triggered | reviewer_node.py | 记忆存储已触发 |
| Memory recall failed | supervisor_node.py | 记忆召回失败 |
| Running summary updated | supervisor_node.py | 阈值压缩执行 |

### 复合回复排查

| 日志关键字 | 文件 | 含义 |
|------------|------|------|
| Mixed-response aggregated | supervisor_graph.py | 车控+对话历史查询的复合回复已聚合 |
| Compound search synthesis | supervisor_graph.py | 车控+生活搜索的复合回复已合成 |

---

## 六、并行任务测试用例参考

### 测试用例 1: 多动作并行车控

用户输入: 打开音乐，关闭车窗，空调调到24度
预期: VehicleExpert 并行执行 Climate/Window/Media 三个动作
检查日志: Dispatch done 中 experts_detail 应包含 vehicle=1
检查结果: expert_results 中应包含 3 条车控结果

### 测试用例 2: 混合意图并行

用户输入: 打开空调，同时帮我查一下附近有什么好吃的
预期: vehicle + lifestyle 两个专家并行执行
检查日志: Mixed-intent: vehicle + non-vehicle
检查结果: expert_results 中应包含车控+搜索两类结果

### 测试用例 3: 复合查询路由

用户输入: 帮我查酒旅服务，推荐一些美食，打开车窗
预期: 启发式识别到 Window_Action，LLM 补充识别酒旅和美食
检查日志: Compound query routed
检查结果: active_experts 应包含 vehicle + lifestyle

### 测试用例 4: 路由防漂移

用户输入: 空调开到27度
预期: 路由到 vehicle 专家，不被导航拦截
检查日志: 不应出现 Route drift detected
检查结果: active_experts 应为 [vehicle]

### 测试用例 5: 对话历史查询+车控

用户输入: 我问了你哪些问题，同时打开天窗
预期: vehicle + chat 两个专家并行执行
检查日志: Mixed-intent 或 Compound query
检查结果: 回复应包含车控执行结果 + 对话历史回顾
