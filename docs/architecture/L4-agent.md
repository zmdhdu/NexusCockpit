# L4 Agent 层 (Multi-Agent)

> 对应代码: `nexus/agent/`

## 职责

编排 Multi-Agent 工作流，实现 Planner → Executor → Responder → Reviewer 协同模式。

## 工作流

```
                    ┌──────────────────────────────────────┐
                    │          用户输入文本                  │
                    └─────────────────┬────────────────────┘
                                      │
                            ┌─────────▼─────────┐
                            │     Planner       │
                            │  · 意图路由        │
                            │  · 记忆召回        │
                            │  · 澄清判断        │
                            │  · 生成执行计划    │
                            └─────────┬─────────┘
                                      │
                            ┌─────────▼─────────┐
                            │     Executor      │
                            │  · 技能调度        │
                            │  · RAG 检索        │
                            │  · LLM 调用        │
                            │  · 外部 API        │
                            └─────────┬─────────┘
                                      │
                            ┌─────────▼─────────┐
                            │    Responder      │
                            │  · 上下文压缩      │
                            │  · LLM 流式生成    │
                            │  · 技能结果透传    │
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

### graph.py — LangGraph 工作流

```python
from nexus.agent.graph import AgentGraph

agent = AgentGraph(
    intent_router=intent_router,
    memory_manager=memory_manager,
    skill_registry=skill_registry,
)

# 非流式
result = await agent.invoke("把空调调到24度", user_id="u1")

# 流式
async for event in agent.stream("今天天气怎么样", user_id="u1"):
    print(event)  # → {"node": "planner", "data": {...}}
```

- 基于 LangGraph `StateGraph`
- 条件路由: Planner 可决定是否需要澄清
- 状态传递: 通过 `AgentState` 对象

### planner.py — 规划 Agent

职责:
1. 调用意图路由器确定用户意图
2. 从记忆系统召回相关上下文
3. 判断是否需要澄清 (歧义/信息不足)
4. 生成执行计划 (调用哪些技能)

### executor.py — 执行 Agent

职责:
1. 根据 Planner 的计划调度技能
2. 如果需要 RAG 检索，调用 GraphRAG
3. 如果需要 LLM 推理，调用 LLM API
4. 收集所有执行结果

### responder.py — 响应 Agent

职责:
1. 压缩上下文 (Token 控制)
2. 如果技能已有结果，直接透传
3. 如果需要 LLM 生成，流式调用
4. 生成最终用户响应

### reviewer.py — 审查 Agent

职责:
1. 检查响应质量 (是否回答了用户问题)
2. 将本次对话存入记忆系统
3. 记录延迟指标
4. 如果质量不合格，触发重试

## Agent State

```python
class AgentState(TypedDict):
    user_input: str              # 用户输入
    user_id: str                 # 用户 ID
    intent: Optional[str]        # 识别的意图
    confidence: float            # 意图置信度
    needs_clarification: bool    # 是否需要澄清
    plan: Optional[list]         # 执行计划
    memory_context: Optional[str]# 记忆上下文
    execution_result: Optional[dict]  # 执行结果
    response: Optional[str]      # 最终响应
    review_passed: bool          # 审查是否通过
    error: Optional[str]         # 错误信息
    metadata: dict               # 元数据 (trace_id, latency 等)
```

## 设计原则

1. **单一职责** — 每个 Agent 只做一件事
2. **可观测** — 每个 Agent 的输入输出都被 Langfuse 追踪
3. **可降级** — LLM 不可用时，技能结果可直通
4. **可扩展** — 新增 Agent 只需实现节点函数并加入图中
