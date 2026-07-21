# ASR 语音识别技术文档

> ⚠️ **注意**: 本文档描述的是 v2.1 独立服务架构。v2.2 已将 ASR/TTS 内嵌至主应用，通过 *_PROVIDER 环境变量切换本地/云端模式。请参考 [架构概览](../architecture/overview.md) 获取最新架构信息。

> 基于 FunASR + SenseVoice-Small 的车载语音识别

## 技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 框架 | FunASR | 阿里达摩院开源，支持多模型，Python 友好 |
| 模型 | SenseVoice-Small | 支持中/英/日/韩多语种，带情感识别，体积小（~500MB） |
| 部署 | 本地 GPU/CPU | 车载场景需低延迟，不依赖云端 |

## 模型信息

- **模型名**: SenseVoiceSmall
- **下载路径**: `models/asr/sensevoice/`
- **支持语种**: 中文、英文、日文、韩文
- **采样率**: 16kHz
- **输入格式**: WAV (PCM 16-bit)
- **输出**: 文本 + 情感标签 + 语种标签

## 代码位置

| 文件 | 功能 |
|------|------|
| `backend_design/nexus/asr/engine.py` | ASR 引擎核心（`ASREngine` 类） |
| `backend_design/nexus/api/routes/asr.py` | ASR REST API（`/asr/transcribe`） |
| `backend_design/nexus/config.py` | ASR 配置（`ASRConfig` 类） |

## API 使用

### 语音识别接口

```http
POST /asr/transcribe
Content-Type: multipart/form-data

file: <audio.wav>
```

**响应**:
```json
{
  "text": "打开空调",
  "language": "zh",
  "emotion": "happy",
  "latency_ms": 120
}
```

## 配置

```env
# .env
FUNASR_MODEL_PATH=./models/asr/sensevoice
```

## v2.2 变更

- 移除了 `asr/engine.py` 中的 `SpeakerVerifier` 类
- 声纹验证统一由 `core/voiceprint.py` 的 `VoiceprintService` 处理
