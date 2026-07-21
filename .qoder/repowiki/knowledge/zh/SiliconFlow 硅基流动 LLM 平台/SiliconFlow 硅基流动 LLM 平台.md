---
kind: external_dependency
name: SiliconFlow 硅基流动 LLM 平台
slug: siliconflow
category: external_dependency
category_hints:
    - vendor_identity
    - auth_protocol
scope:
    - '**'
---

### SiliconFlow 硅基流动 LLM 平台
- **角色**：OpenAI 兼容的云端大模型服务平台，提供 LLM 对话、Embedding、Rerank 能力
- **集成点**：通过 ARK_API_KEY 和 ARK_BASE_URL 配置，统一接入 DeepSeek-V3、Qwen3-Embedding-4B 等模型
- **认证协议**：Bearer Token 认证，OpenAI 兼容接口格式，支持 `/chat/completions`、`/embeddings`、`/rerank` 端点
- **关键特性**：免费档可用、一站式平台、代码零改动切换供应商（火山方舟/硅基流动）