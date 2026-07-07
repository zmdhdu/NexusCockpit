# 本地 LLM 模型 (可选)

本目录存放本地 LLM 模型，仅在 `USE_LOCAL_LLM=true` 时需要。

默认使用云端 Ark API (DeepSeek-V3)，无需下载本地模型。

## 下载方式

```bash
# 安装 HuggingFace Hub
pip install huggingface_hub

# 下载 Qwen2.5-7B-Instruct
huggingface-cli download Qwen/Qwen2.5-7B-Instruct --local-dir ./
```

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LOCAL_LLM_MODEL_PATH` | `./models/llm/qwen` | 模型路径 |
| `USE_LOCAL_LLM` | `false` | 是否启用本地 LLM |

详见 [SETUP.md](../../docs/deployment/SETUP.md)。
