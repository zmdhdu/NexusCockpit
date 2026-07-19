---
kind: external_dependency
name: Langfuse LLM 可观测性平台
slug: langfuse
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### Langfuse LLM 可观测性平台
- **角色**: 专为 LLM 应用设计的追踪和监控平台
- **集成点**: `backend_design/nexus/observability/langfuse.py` 追踪监控器
- **关键功能**: Agent 调用链路追踪、LLM 请求记录、性能指标收集
- **部署模式**: 云端 SaaS (cloud.langfuse.com) 或自建实例
- **配置要求**: 需要配置 public_key 和 secret_key 才能启用