---
kind: external_dependency
name: 硅基流动 — OpenAI 兼容 LLM/Embedding/Rerank 服务
slug: siliconflow
category: external_dependency
category_hints:
    - vendor_identity
    - auth_protocol
scope:
    - '**'
---

### 供应商身份
硅基流动（SiliconFlow）是本项目默认的云端 LLM 提供商，提供 OpenAI 兼容的 chat/completions、embeddings 和 rerank API。默认 base_url 为 `https://api.siliconflow.cn/v1`。

### 在本项目中的角色
- **LLM 对话**：DeepSeek-V3 模型通过 `openai.AsyncOpenAI` SDK 调用
- **Embedding 向量化**：Qwen/Qwen3-Embedding-4B（2560 维），用于语义缓存和向量检索
- **Rerank 重排**：bge-reranker-v2-m3 CrossEncoder 模型，对 RRF 融合结果做二次排序

### 集成方式
通过 Pydantic Settings 的 `LLMConfig` 类集中管理：
- `ark_api_key` / `ark_base_url` 从 `.env` 的 `ARK_API_KEY` / `ARK_BASE_URL` 读取
- `embedding_model` / `embedding_dim` 控制 Embedding 模型及维度
- 支持切换火山方舟（`https://ark.cn-beijing.volces.com/api/v3`）作为备选供应商

### 认证协议
使用 OpenAI 兼容的 Bearer Token 认证，API Key 通过 `Authorization: Bearer <key>` 头传递。生产环境必须覆盖默认值，避免弱密钥泄露。

### 双模式部署
通过 `RERANKER_PROVIDER=cloud` 可切换到硅基流动的免费 Rerank API，无需本地部署 bge-reranker 模型。

注意：具体 API 参数和限流策略需参考硅基流动官方文档。