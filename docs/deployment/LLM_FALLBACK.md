# LLM 本地降级部署指南

> 云端 LLM 不可用时降级到本地 Qwen3.5-4B 模型

## 架构

```
用户请求 → ResponderAgent
              ├─ try: 云端 LLM (DeepSeek-V3, 硅基流动)
              └─ catch: 本地 LLM (Qwen3.5-4B, llama.cpp)
                          └─ 返回本地推理结果
```

## 前置条件

1. 下载 Qwen3.5-4B GGUF 模型
2. 安装 llama.cpp 并启动 OpenAI 兼容服务
3. 配置 `.env` 启用降级

## 部署步骤

### 1. 下载模型

```bash
# 下载 Qwen3.5-4B GGUF 量化模型
mkdir -p models/llm/qwen3.5-4b
cd models/llm/qwen3.5-4b

# 从 HuggingFace 下载（示例）
# wget https://huggingface.co/Qwen/Qwen3.5-4B-Instruct-GGUF/resolve/main/qwen3.5-4b-instruct-q4_k_m.gguf
```

### 2. 启动 llama.cpp

```bash
# 使用 Docker
docker run -d \
  --name llama-cpp \
  -p 8082:8082 \
  -v ./models/llm/qwen3.5-4b:/models \
  ghcr.io/ggerganov/llama.cpp:server-latest \
  -m /models/qwen3.5-4b-instruct-q4_k_m.gguf \
  --host 0.0.0.0 \
  --port 8082 \
  --ctx-size 4096 \
  --n-gpu-layers 35  # GPU 加速层数
```

### 3. 配置 .env

```env
# 启用本地 LLM 降级
LLM_FALLBACK_ENABLED=true
LLM_FALLBACK_BASE_URL=http://127.0.0.1:8082/v1
LLM_FALLBACK_MODEL=qwen3.5-4b-local
LLM_FALLBACK_API_KEY=  # llama.cpp 默认无需 API Key
LLM_FALLBACK_TIMEOUT=60
```

### 4. 验证

```bash
# 测试 llama.cpp 服务
curl http://127.0.0.1:8082/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5-4b-local",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

## 降级触发条件

- 云端 LLM API 超时
- 云端 LLM 返回错误（429 限流 / 500 服务器错误）
- 网络连接中断

## 代码位置

| 文件 | 功能 |
|------|------|
| `backend_design/nexus/agent/responder.py` | LLM 降级逻辑 |
| `backend_design/nexus/config.py` | `LLMConfig.fallback_*` 配置字段 |

## 注意事项

1. **本地模型质量**: Qwen3.5-4B 比 DeepSeek-V3 能力弱，降级后回答质量可能下降
2. **推理速度**: 本地推理依赖 GPU/CPU，可能比云端慢
3. **内存占用**: 4B 量化模型约需 4-6GB 内存
4. **并发能力**: llama.cpp 单实例并发能力有限
