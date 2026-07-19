---
kind: external_dependency
name: LangGraph Agent 编排框架
slug: langgraph
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

### LangGraph Agent 编排框架
- **角色**: Multi-Agent 工作流编排核心，实现 Supervisor + 5 Expert Agents 架构
- **集成点**: `backend_design/nexus/agent/supervisor_graph.py` 中的 SupervisorGraph 类
- **使用模式**: 有状态图执行、条件路由、并行专家 Agent 调用、反思校验流程
- **关键特性**: 检查点持久化（AsyncSqliteSaver）、工具调用、记忆系统集成
- **降级策略**: 云端 DeepSeek-V3 → 本地 Qwen3.5-4B (llama.cpp) 自动降级