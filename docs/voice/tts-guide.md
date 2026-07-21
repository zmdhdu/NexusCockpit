# TTS 语音合成技术文档

> ⚠️ **注意**: 本文档描述的是 v2.1 独立服务架构。v2.2 已将 ASR/TTS 内嵌至主应用，通过 *_PROVIDER 环境变量切换本地/云端模式。请参考 [架构概览](../architecture/overview.md) 获取最新架构信息。

> 基于 CosyVoice 的车载语音合成

## 技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 模型 | CosyVoice-300M | 阿里通义实验室开源，支持音色克隆，中文自然度高 |
| 部署 | 本地 GPU | 车载场景需低延迟 |

## 模型信息

- **模型名**: CosyVoice
- **下载路径**: `models/tts/cosyvoice/`
- **功能**: 文本转语音、音色克隆
- **采样率**: 22.05kHz
- **输出格式**: WAV (PCM 16-bit)

## 代码位置

| 文件 | 功能 |
|------|------|
| `backend_design/nexus/tts/engine.py` | TTS 引擎核心（`TTSEngine` 类） |
| `backend_design/nexus/api/routes/` | TTS REST API |
| `backend_design/nexus/config.py` | TTS 配置（`ASRConfig.cosyvoice_model_path`） |

## 配置

```env
# .env
COSYVOICE_MODEL_PATH=./models/tts/cosyvoice
```

## 降级策略

1. CosyVoice 模型不可用 → 返回文本回复（无声纹验证）
2. GPU 不可用 → 自动切换 CPU 推理（延迟增加）
