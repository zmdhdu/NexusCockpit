# 语音交互系统技术文档

> NexusCockpit 语音交互系统全链路技术说明

## 系统架构

```
用户语音 → ASR(语音转文字) → 意图路由 → Agent 工作流 → TTS(文字转语音) → 用户
                ↓                                         ↑
            声纹识别(可选) → 个性化服务 → 注入用户画像 ─┘
```

## 模块清单

| 模块 | 技术栈 | 模型 | 文档 |
|------|--------|------|------|
| ASR 语音识别 | FunASR | SenseVoice-Small | [asr-guide.md](./asr-guide.md) |
| TTS 语音合成 | CosyVoice | CosyVoice-300M | [tts-guide.md](./tts-guide.md) |
| 声纹识别 | 3D-Speaker | CAM++ | [voiceprint-guide.md](./voiceprint-guide.md) |
| 音频管线 | FastAPI StaticFiles + HTML5 Audio | - | [audio-pipeline-guide.md](./audio-pipeline-guide.md) |

## v2.2 变更

### 新增
- **PersonalizationService**: 声纹识别后匹配用户偏好，注入到 Prompt
- **LLM 本地降级**: 云端 LLM 不可用时自动降级到本地 Qwen3.5-4B（llama.cpp）
- **动态音乐扫描**: MockVehicleBus 动态扫描 `assets/audio/music/` 目录

### 修复
- **VoiceprintService mock 模式**: 模型不可用时返回 None（不再返回假随机向量）
- **前端音乐 URL**: 使用后端返回的 `track.url`（不再硬编码 `track_01.wav`）

### 精简
- 移除 `asr/engine.py` 中的 `SpeakerVerifier` 类（与 `core/voiceprint.py` 重复）
