---
kind: external_dependency
name: 火山方舟 LLM 服务平台
slug: volcengine-ark
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### 火山方舟 LLM 服务平台
- **角色**: LLM 供应商备选方案，同样提供 OpenAI 兼容接口
- **集成点**: 通过修改 ARK_BASE_URL 即可从硅基流动切换到火山方舟
- **认证方式**: 相同的 ARK_API_KEY 格式，不同 base_url
- **服务地址**: https://ark.cn-beijing.volces.com/api/v3
- **适用场景**: 当硅基流动不可用时的故障转移目标