---
kind: external_dependency
name: LangGraph 多Agent编排框架
slug: langgraph
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
source_files:
    - backend_design/nexus/agent/supervisor_graph.py
---

### LangGraph 多Agent编排框架
- **角色**: 作为 Supervisor + 5 Expert Agents 的编排框架，实现意图路由、记忆召回、专家分派等核心能力
- **集成点**: supervisor_graph.py 中定义 Agent 状态图和节点流转逻辑
- **使用模式**: 通过 GraphRAG 进行检索增强，结合 Reflection + Reviewer 双重校验降低幻觉风险
- **架构决策**: 保留现有 Multi-Agent 架构，仅优化内部实现，不替换为单 Agent 方案
- **验证**: 需对照官方文档确认具体 API 和参数配置