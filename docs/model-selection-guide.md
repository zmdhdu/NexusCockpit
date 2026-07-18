# NexusCockpit 模型选型对比分析

> **文档用途**：本项目所有 AI 模型的选型对比与技术评估，供技术决策和面试参考。
> **创建日期**：2026-07-18
> **对应代码版本**：v2.1
> **维护规范**：每次模型变更时同步更新本文档，详见 `分析报告.md` 第十三章

---

## 一、LLM 大语言模型选型

### 1.1 云端主模型对比

| 维度 | DeepSeek-V3（当前默认） | DeepSeek-V4-Flash（推荐升级） | DeepSeek-R1 | Qwen2.5-72B-Instruct |
|------|------------------------|-------------------------------|-------------|----------------------|
| **硅基流动 model_id** | `deepseek-ai/DeepSeek-V3` | `deepseek-ai/DeepSeek-V4-Flash` | `deepseek-ai/DeepSeek-R1` | `Qwen/Qwen2.5-72B-Instruct` |
| **参数量** | 671B (MoE, 37B 激活) | 待确认（Flash 版通常为轻量） | 671B (MoE) | 72B |
| **上下文长度** | 64K | 待确认 | 64K | 32K |
| **推理速度** | 快（50-100 tok/s） | 很快（Flash 优化） | 慢（含 CoT 链） | 快 |
| **生成质量** | 优秀 | 优秀（V4 迭代） | 优秀（推理任务） | 优秀 |
| **Function Calling** | 优秀 | 优秀 | 良好 | 优秀 |
| **中文能力** | 优秀 | 优秀 | 优秀 | 优秀 |
| **成本** | 中 | 低（Flash 定位经济） | 高（token 多） | 中 |
| **离线可用** | 否 | 否 | 否 | 否 |
| **硅基流动链接** | [模型广场](https://cloud.siliconflow.cn/models?target=deepseek-ai/DeepSeek-V3) | [模型广场](https://cloud.siliconflow.cn/models?target=deepseek-ai/DeepSeek-V4-Flash) | [模型广场](https://cloud.siliconflow.cn/models?target=deepseek-ai/DeepSeek-R1) | [模型广场](https://cloud.siliconflow.cn/models?target=Qwen/Qwen2.5-72B-Instruct) |

### 1.2 本地降级模型对比

| 维度 | Qwen3.5-4B-Q4_K_M ✅（已就位） | Qwen2.5-7B-Instruct Q4_K_M | Qwen2.5-3B-Instruct Q4_K_M |
|------|----------------------------|----------------------------|----------------------------------|
| **参数量** | 4B | 7B | 3B |
| **量化后体积** | ~2.5GB | ~4.5GB | ~2GB |
| **内存占用** | ~4-5GB | ~6-8GB | ~3-4GB |
| **显存占用(Q4)** | ~3GB | ~5GB | ~2.5GB |
| **CPU 推理速度** | 8-15 tok/s | 5-10 tok/s | 10-20 tok/s |
| **GPU 推理速度** | 35-50 tok/s | 25-40 tok/s | 40-60 tok/s |
| **上下文长度** | 待确认 | 32K | 32K |
| **中文能力** | 良好 | 良好 | 一般 |
| **Function Calling** | 基本可用 | 良好 | 基本可用 |
| **模型路径** | `models/llm/qwen/Qwen3.5-4B-Q4_K_M.gguf` | [HuggingFace](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF) | [HuggingFace](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF) |
| **状态** | ✅ 已下载就位 | 备选 | 备选 |

### 1.3 LLM 选型结论

```
主力模型:  DeepSeek-V4-Flash (云端，硅基流动，经济+快速)
          ↓ 网络中断/限流时自动降级
降级模型:  Qwen3.5-4B-Q4_K_M (本地，llama.cpp，离线可用，已就位)
          ↓ 本地模型也不可用时
最终降级:  缓存命中 / 规则兜底 / 返回友好提示
```

---

## 二、ASR 语音识别模型选型

### 2.1 模型对比

| 维度 | SenseVoice-Small（当前 ✅） | Qwen3-ASR-0.6B | Qwen3-ASR-1.7B | Whisper-Large-v3 |
|------|----------------------------|-----------------|------------------|-------------------|
| **参数量** | ~234M | 600M | 1700M | 1550M |
| **模型体积** | ~500MB | ~1.2GB | ~3.4GB | ~3GB |
| **显存占用** | ~1GB | ~2.5GB | ~7GB | ~6GB |
| **CPU 推理** | 快（RTF<0.3） | 中 | 慢 | 慢 |
| **GPU 推理** | 很快 | 快 | 中 | 中 |
| **支持语言** | 中/英/日/韩/粤 5语种 | 中/英 | 中/英 | 99语种 |
| **ITN 逆文本归一化** | ✅ 内置 | 待确认 | 待确认 | ✅ 内置 |
| **标点恢复** | ✅ 内置 | 待确认 | 待确认 | ✅ 内置 |
| **情绪识别** | ✅ 支持 | ❌ | ❌ | ❌ |
| **音频事件检测** | ✅ 支持（掌声/笑声/哭声） | ❌ | ❌ | ❌ |
| **工具链** | FunASR（完善） | ModelScope | ModelScope | OpenAI Whisper |
| **成熟度** | 高 | 新发布 | 新发布 | 高 |
| **车载适配** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |

### 2.2 ASR 选型结论

**保持 SenseVoice-Small**。理由：
1. 资源效率：234M 参数，CPU 可流畅运行
2. 功能最全：独有情绪识别+音频事件检测，车载场景价值大
3. 多语言：支持粤语，适合国内复杂语言环境
4. 生态成熟：FunASR 工具链完善，后处理开箱即用

---

## 三、TTS 语音合成模型选型

### 3.1 模型对比

| 维度 | CosyVoice（当前 ✅） | Qwen3-TTS-12Hz-0.6B-Base | ChatTTS | Edge-TTS |
|------|----------------------|---------------------------|---------|----------|
| **参数量** | ~300M | 600M | ~400M | 云端（无本地） |
| **音色克隆** | ✅ Zero-shot（3秒音频） | ❌ Base版不支持 | ❌ | ❌ |
| **流式合成** | ✅ 支持 | 待确认 | ✅ | ✅ |
| **预训练音色** | ✅ 多个内置 | ❌ 需 fine-tune | ❌ | ✅ 多语言 |
| **跨语言合成** | ✅ 支持 | 待确认 | ❌ | ✅ |
| **情绪控制** | ✅ 支持 | 待确认 | ✅ | ❌ |
| **采样率** | 22050Hz | 待确认 | 24000Hz | 24000Hz |
| **离线可用** | ✅ | ✅ | ✅ | ❌ 需网络 |
| **成熟度** | 高（阿里落地） | 新发布 | 中 | 高（微软） |
| **车载适配** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

### 3.2 TTS 选型结论

**保持 CosyVoice**。理由：
1. 音色克隆：Zero-shot 克隆是个性化语音核心
2. 开箱即用：内置多个预训练音色
3. 流式合成：降低首字延迟
4. 离线可用：端侧部署不依赖网络

---

## 四、声纹识别模型选型

### 4.1 模型对比

| 维度 | CAM++（当前 ✅） | ERes2Net Large | ECAPA-TDNN |
|------|------------------|----------------|------------|
| **模型 ID** | `iic/speech_campplus_sv_zh-cn_16k-common` | `iic/speech_eres2net_large_sv_zh-cn_3dspeaker_16k` | — |
| **参数量** | ~20M | ~170M | ~80M |
| **Embedding 维度** | 192 | 192 | 512 |
| **模型体积** | ~80MB | ~680MB | ~320MB |
| **显存占用** | ~300MB | ~1.5GB | ~800MB |
| **CPU 推理** | <50ms | ~200ms | ~100ms |
| **EER（等错误率）** | ~3.5% | ~1.5% | ~2.5% |
| **注册音频** | 3条×3-10秒 | 3条×5-10秒 | 3条×3-10秒 |
| **适用场景** | 资源受限 | 高精度 | 通用 |
| **车载适配** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

### 4.2 声纹选型结论

**保持 CAM++**。理由：
1. 资源效率：80MB，CPU <50ms，车载友好
2. 精度够用：车载用户数少（1-5人），EER 3.5% 足够
3. 接口兼容：同为 3D-Speaker 框架，切换成本低

---

## 五、Embedding 向量模型选型

### 5.1 模型对比

| 维度 | Qwen3-Embedding-4B（当前 ✅） | BAAI/bge-m3 | text-embedding-3-large |
|------|-------------------------------|-------------|------------------------|
| **硅基流动 model_id** | `Qwen/Qwen3-Embedding-4B` | `BAAI/bge-m3` | — |
| **向量维度** | 2560 | 1024 | 3072 |
| **多语言** | ✅ | ✅ | ✅ |
| **成本** | 免费（硅基流动） | 免费（硅基流动） | OpenAI 计费 |
| **当前使用** | ✅ | 备选 | 不推荐 |

### 5.2 Embedding 选型结论

**保持 Qwen3-Embedding-4B**。若需降级到 bge-m3，需同步修改 `EMBEDDING_DIM=1024` 并重建 Milvus collection。

---

## 六、Rerank 重排模型选型

### 6.1 模型对比

| 维度 | bge-reranker-v2-m3（当前 ✅） | bge-reranker-v2-gemma | Cohere rerank |
|------|-------------------------------|----------------------|---------------|
| **模型路径** | `./models/reranker/bge-reranker-v2-m3` | — | 云端 API |
| **本地/云端** | 本地（默认） | 本地 | 云端 |
| **多语言** | ✅ | ✅ | ✅ |
| **成本** | 0 | 0 | 按次计费 |
| **硅基流动** | `BAAI/bge-reranker-v2-m3`（可选云端） | — | — |

### 6.2 Rerank 选型结论

**保持 bge-reranker-v2-m3**，支持本地+云端双模式。

---

## 七、最终模型组合

| 模型类型 | 选定模型 | 部署方式 | 降级方案 |
|----------|----------|----------|----------|
| **LLM 主力** | DeepSeek-V4-Flash | 云端（硅基流动） | → 本地 Qwen3.5-4B-Q4_K_M |
| **LLM 降级** | Qwen3.5-4B-Q4_K_M | 本地（llama.cpp，已就位） | → 缓存/规则兜底 |
| **ASR** | SenseVoice-Small | 本地（FunASR） | → 返回空字符串+warn |
| **TTS** | CosyVoice | 本地 | → 返回空音频+warn |
| **声纹** | CAM++ | 本地（3D-Speaker） | → 返回未验证+warn |
| **Embedding** | Qwen3-Embedding-4B | 云端（硅基流动） | → bge-m3（需改维度） |
| **Rerank** | bge-reranker-v2-m3 | 本地/云端双模式 | → 跳过重排 |

---

## 八、模型下载地址汇总

| 模型 | 下载地址 | 放置路径 |
|------|----------|----------|
| SenseVoice-Small | [ModelScope](https://modelscope.cn/models/iic/SenseVoiceSmall) | `models/asr/sensevoice/` |
| CosyVoice | [ModelScope](https://modelscope.cn/models/iic/CosyVoice-300M) | `models/tts/cosyvoice/` |
| CAM++ | [ModelScope](https://modelscope.cn/models/iic/speech_campplus_sv_zh-cn_16k-common) | `models/sv/cam_plus/` |
| bge-reranker-v2-m3 | [HuggingFace](https://huggingface.co/BAAI/bge-reranker-v2-m3) | `models/reranker/bge-reranker-v2-m3/` |
| Qwen3.5-4B-Q4_K_M | 已下载 | `models/llm/qwen/Qwen3.5-4B-Q4_K_M.gguf` |
| Qwen2.5-7B-Instruct-GGUF | [HuggingFace](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF) | `models/llm/qwen/`（备选） |
| llama.cpp (预编译) | [GitHub Releases](https://github.com/ggerganov/llama.cpp/releases) | `models/llm/llama.cpp/` |
