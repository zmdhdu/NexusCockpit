# 本地 LLM 模型 (可选)

本目录存放本地 LLM 模型，仅在 LLM 降级模式下需要。

默认使用云端火山方舟 ARK API (DeepSeek-V3)，无需下载本地模型。

## 下载方式

```bash
# 安装 HuggingFace Hub
pip install huggingface_hub

# 下载 Qwen3.5-4B (GGUF 量化版)
huggingface-cli download Qwen/Qwen3.5-4B-Instruct-GGUF --local-dir ./
```

> 当前已包含 `Qwen3.5-4B-Q4_K_M.gguf` 量化模型，配合 `models/llm/llama.cpp/` 中的 llama.cpp 推理引擎使用。

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LLM_FALLBACK` | `local` | LLM 降级模式：`local`=本地 llama.cpp |
| `LOCAL_LLM_MODEL_PATH` | `./models/llm/qwen` | 本地模型路径 |

详见 [LLM 降级部署指南](../../docs/交付版文档包/10-LLM降级部署指南.md) 或 [部署安装手册](../../docs/交付版文档包/01-部署安装手册.md)。
