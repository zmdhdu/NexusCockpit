# L4 Agent 层 (Multi-Agent)

> 对应代码: `nexus/agent/` + `nexus/intent/`
> 最后更新: 2026-07-14

## 职责

编排 Multi-Agent 工作流，v2.0 升级为 **Supervisor + 5 专家智能体** 架构：
- Supervisor 负责记忆召回、意图路由、专家分派决策
- 5 个专家 Agent 并行执行各自领域的技能
- Responder 汇总专家输出，生成最终回复
- Reflection (v2.2) 对 LLM 输出做事实性/一致性/无幻觉检查
- Reviewer 质量检查 + 记忆存储 + 延迟统计

> **v2.2.5 更新**: 新增闲聊预校验（Pre-check）和幻觉兜底（Post-check），
> 防止 LLM 编造对话历史。流式模式改为"先生成完整回复 → 校验 → 再发送"。

## 工作流 (v2.0)

```
                    ┌──────────────────────────────────────┐
                    │          用户输入文本                  │
                    └─────────────────┬────────────────────┘
                                      │
                            ┌─────────▼─────────┐
                            │    Supervisor     │
                            │  · 记忆召回        │
                            │  · 意图路由        │
                            │  · 澄清判断        │
                            │  · 专家分派决策    │
                            └─────────┬─────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
            ┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐
            │Vehicle Expert│  │  Nav Expert  │  │Lifestyle Exp │
            │(空调/车窗/座椅│  │(路线规划/POI) │  │(搜索/点餐/POI)│
            │/媒体/状态)   │  │              │  │              │
            └───────┬──────┘  └───────┬──────┘  └───────┬──────┘
                    │                 │                 │
            ┌───────▼──────┐  ┌───────▼──────┐
            │ Health Expert│  │  Chat Expert │
            │(诊断/故障码/ │  │(闲聊/知识库  │
            │ 保养)        │  │  问答)       │
            └───────┬──────┘  └───────┬──────┘
                    │                 │
                    └────────┬────────┘
                             │
                   ┌─────────▼─────────┐
                   │    Responder      │
                   │  · 汇总专家输出    │
                   │  · LLM 回复生成    │
                   │  · 技能结果透传    │
                   │  · v2.2.5: 预校验  │
                   │    + 后校验        │
                   └─────────┬─────────┘
                             │
                   ┌─────────▼─────────┐
                   │   Reflection      │
                   │  (v2.2 新增)       │
                   │  · 事实性检查      │
                   │  · 无幻觉检查      │
                   │  · v2.2.5: 兜底    │
                   │    幻觉检测        │
                   └─────────┬─────────┘
                             │
                   ┌─────────▼─────────┐
                   │     Reviewer      │
                   │  · 响应质量检查    │
                   │  · 记忆存储        │
                   │  · 延迟指标        │
                   └─────────┬─────────┘
                             │
                   ┌─────────▼─────────┐
                   │   返回给用户       │
                   └───────────────────┘
```

## 模块清单

### supervisor_graph.py — v2.0 编排核心

```python
from nexus.agent.supervisor_graph import SupervisorGraph
from nexus.models.state import create_initial_state

agent = SupervisorGraph(
    intent_router=intent_router,
    memory_manager=memory_manager,
    skill_registry=skill_registry,
    checkpoint_saver=checkpoint_saver,  # SqliteSaver (可选)
)

# 非流式
state = create_initial_state(user_input="把空调调到24度", user_id="u1")
result = await agent.invoke(state)

# 流式 (纯文本)
async for chunk in agent.stream(state):
    print(chunk)

# 流式 (结构化事件)
async for event in agent.stream_with_events(state):
    # event: {"type": "intent"/"experts"/"action"/"chunk"/"done", "data": {...}}
    print(event)
```

- 基于 LangGraph `StateGraph`，TypedDict 状态管理
- Supervisor 条件路由: 需要澄清直连 Responder / 否则分派专家
- 专家并行执行: `asyncio.gather` 同时调用所有活跃专家
- `expert_results` 通过 `Annotated[list, add]` reducer 自动累加
- 支持 `SqliteSaver` checkpoint 持久化（thread_id = session_id）
- v2.2: Reflection 节点对工具/搜索类回复做 LLM 反思校验
- v2.2.4: 系统提示词注入当前东八区时间（`current_time` 变量）
- v2.2.5: 闲聊预校验（`_pre_check_chat_response`）拦截无历史的历史查询
- v2.2.5: 闲聊后校验（`_post_check_chat_response`）检测编造对话历史
- v2.2.5: 流式闲聊改为"先生成完整回复 → 校验 → 再发送"，防止未校验内容呈现给用户

### experts/ — 5 个专家 Agent

| 专家 | 文件 | 技能分组 | 职责 |
|------|------|----------|------|
| VehicleExpert | `vehicle_expert.py` | VEHICLE | 空调/车窗/座椅/媒体/状态查询 |
| NavExpert | `nav_expert.py` | NAVIGATION | 路线规划、兴趣点检索 |
| LifestyleExpert | `lifestyle_expert.py` | LIFESTYLE | 搜索/点餐/本地生活/日程提醒 |
| HealthExpert | `health_expert.py` | HEALTH | 车辆诊断/故障码翻译/保养建议 |
| ChatExpert | `chat_expert.py` | CHAT | 闲聊/知识库问答/声纹注册 |

每个专家继承 `BaseExpertAgent`，实现 `_execute()` 方法：
1. 从 `active_experts` 检查是否被 Supervisor 分派
2. 从 `intent` 提取对应动作字段
3. 调用 `SkillRegistry` 执行技能
4. 返回 partial state update（不修改原 state）

### experts/base.py — 专家基类

```python
from nexus.agent.experts.base import BaseExpertAgent

class MyExpert(BaseExpertAgent):
    expert_name = "my_expert"
    group = SkillGroup.LIFESTYLE

    async def _execute(self, state: SupervisorState) -> Dict[str, Any]:
        # 执行技能逻辑
        return self._build_expert_result(
            action="my_action",
            reply="处理结果",
            handled=True,
        )
```

### v1.0 兼容模块 (DEPRECATED)

以下 v1.0 模块仍保留但已标记为 DEPRECATED，`main.py` 已切换到 `SupervisorGraph`：

| 模块 | 状态 | 说明 |
|------|------|------|
| `graph.py` | DEPRECATED | v1.0 AgentGraph，已被 SupervisorGraph 替代 |
| `planner.py` | DEPRECATED | v1.0 规划 Agent，职责已并入 Supervisor 节点 |
| `executor.py` | DEPRECATED | v1.0 执行 Agent，职责已拆分到 5 个专家 |
| `responder.py` | ✅ 复用 | 上下文压缩 + LLM 调用逻辑仍被 SupervisorGraph 使用 |
| `reviewer.py` | ✅ 复用 | 质量检查 + 记忆存储逻辑仍被 SupervisorGraph 使用 |

## Supervisor State (v2.0)

```python
class SupervisorState(TypedDict, total=False):
    """v2.0 Supervisor 多智能体工作流共享状态。"""
    # 输入
    user_input: str
    user_id: str
    session_id: str

    # 记忆召回 (reducer: add)
    recalled_memories: Annotated[List[str], add]
    memory_str: str
    user_profile: Dict[str, Any]

    # 意图路由 / Supervisor 分派
    intent: Dict[str, Any]
    intent_source: str
    need_clarification: bool
    clarification_prompt: str
    active_experts: List[str]           # Supervisor 决定分派给哪些专家
    query_type: str                     # memory / knowledge / hybrid

    # 专家输出 (reducer: add — 并行累加)
    expert_results: Annotated[List[Dict[str, Any]], add]

    # 兼容 v1.0 技能字段
    skill_result: Any                   # DispatchResult
    skill_handled: bool
    skill_action: str
    search_context: str
    # 副作用标记: 车控等操作会修改车辆状态，此类响应禁止写入语义缓存
    has_side_effect: bool

    # LLM 对话 (reducer: add)
    history: Annotated[List[Dict[str, str]], add]
    running_summary: str
    llm_response: str

    # 最终输出 (reducer: merge_dict)
    final_response: str
    metadata: Annotated[Dict[str, Any], merge_dict]

    # 可观测性 (reducer: merge_dict)
    trace_id: str
    span_ids: Annotated[Dict[str, str], merge_dict]
    latency_ms: float
```

> **reducer 说明**:
> - `Annotated[list, add]`: 多节点并行写入时列表自动拼接（如 `expert_results`、`history`）
> - `Annotated[dict, merge_dict]`: 多节点并行写入时字典自动合并（如 `metadata`、`span_ids`）
> - 无 Annotated 的字段: 最后一个写入者覆盖（last writer wins）

> **注意**: `has_side_effect` 字段是安全修复新增的关键标志。当专家执行车控指令时设为 `True`，chat.py 会据此跳过缓存写入，防止"打开空调"命中缓存后车控不执行的安全事故。

## Prompt 模板 (nexus/prompts/)

v2.0 新增外置 Prompt 模板管理：

```python
from nexus.prompts import PromptManager

pm = PromptManager()
system_msg = pm.render("chat", user_profile={}, memory="用户喜欢24度")
```

| 模板文件 | 用途 |
|----------|------|
| `chat.md` | 闲聊系统提示词 (v2.3: 含 `current_time` + 记忆使用约束) |
| `clarification.md` | 澄清追问提示词 |
| `memory_extract.md` | 记忆提取提示词 |
| `search.md` | 搜索结果组织提示词 |
| `vehicle.md` | 车控回复提示词 |

## 设计原则

1. **Supervisor 模式** — Supervisor 统一调度，专家各司其职
2. **并行执行** — 多个专家通过 `asyncio.gather` 并行，`expert_results` 自动累加
3. **可观测** — 每个 Agent 的输入输出都被 Langfuse 追踪
4. **可降级** — LLM 不可用时，技能结果可直通
5. **可扩展** — 新增专家只需实现 `BaseExpertAgent` 并在 `SupervisorGraph.experts` 中注册
6. **Checkpoint** — 支持 `SqliteSaver` 持久化，会话中断可恢复
