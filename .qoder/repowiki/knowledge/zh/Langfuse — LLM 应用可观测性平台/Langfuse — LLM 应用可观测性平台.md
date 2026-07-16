---
kind: external_dependency
name: Langfuse — LLM 应用可观测性平台
slug: langfuse
category: external_dependency
category_hints:
    - vendor_identity
    - framework_behavior
scope:
    - '**'
---

### 供应商身份
Langfuse 专为 LLM 应用设计的可观测性平台，支持自托管和云端部署。

### 在本项目中的角色
- **LLM 调用追踪**：记录每次 Agent 调用的完整链路、token 消耗、延迟等指标
- **Prompt 管理**：版本化的 prompt 模板管理和 A/B 测试
- **性能分析**：可视化展示各节点耗时、错误率等关键指标

### 集成方式
通过 Pydantic Settings 的 `LangfuseConfig` 类管理：
- `public_key/secret_key` 认证凭据
- `host` 服务地址（默认 `https://cloud.langfuse.com`）
- 仅当 public_key 和 secret_key 都配置时才启用

### 框架行为
- 当前集成较浅（128 行），主要做空对象降级包装（NullTrace/NullSpan/NullGeneration）
- SupervisorGraph 中每个节点的耗时、LLM 调用详情等**没有自动追踪到 Langfuse**
- 建议在每个节点函数中手动创建 span，记录 token 消耗、latency、reflection 结果等

### 约束条件
- 云端版按 observation 数计费，自托管版免费但需自行维护
- 与 LangSmith 的区别：Langfuse 支持自托管且框架无关，更适合本项目的异构架构