---
kind: external_dependency
name: Langfuse LLM 追踪平台
slug: langfuse
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### Langfuse LLM 追踪平台
- **角色**：LLM 应用专用可观测性平台，追踪对话链路、性能指标、成本分析
- **集成点**：通过 LANGFUSE_PUBLIC_KEY 和 LANGFUSE_SECRET_KEY 配置，默认指向 cloud.langfuse.com
- **使用模式**：空 Key 自动降级不阻塞，结构化日志与 Prometheus 指标互补
- **关键特性**：LLM 专用监控、对话回放、性能分析、成本追踪