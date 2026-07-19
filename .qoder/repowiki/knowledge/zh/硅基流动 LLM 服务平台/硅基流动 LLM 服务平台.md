---
kind: external_dependency
name: 硅基流动 LLM 服务平台
slug: siliconflow
category: external_dependency
category_hints:
    - vendor_identity
    - auth_protocol
scope:
    - '**'
---

### 硅基流动 LLM 服务平台
- **角色**: 默认 LLM 供应商，提供 OpenAI 兼容的对话、Embedding、Rerank API
- **集成点**: `backend_design/nexus/config.py` LLMConfig 配置类
- **认证方式**: ARK_API_KEY + ARK_BASE_URL (OpenAI 兼容接口)
- **服务类型**: DeepSeek-V3 对话模型、Qwen3-Embedding-4B 向量化、bge-reranker-v2-m3 重排
- **免费额度**: Embedding 和 Rerank API 提供免费调用额度