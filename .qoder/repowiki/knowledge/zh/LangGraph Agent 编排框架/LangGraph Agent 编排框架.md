---
kind: external_dependency
name: LangGraph Agent 编排框架
slug: langgraph
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### LangGraph Agent 编排框架
- **角色**：Multi-Agent 工作流编排核心，实现 Supervisor + 5 Expert Agents 的并行协作架构
- **集成点**：`backend_design/nexus/agent/supervisor_graph.py` 作为编排核心，管理专家 Agent 的调度与结果聚合
- **使用模式**：有状态图执行、条件路由、并行节点执行，支持 Reflection 和 Reviewer 质量检查流程
- **关键特性**：与 LangChain 生态兼容，支持 Checkpoint 持久化，适合复杂 AI 应用的工作流编排