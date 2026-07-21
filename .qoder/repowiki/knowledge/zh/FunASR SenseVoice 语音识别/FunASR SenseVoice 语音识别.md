---
kind: external_dependency
name: FunASR SenseVoice 语音识别
slug: funasr-sensevoice
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### FunASR SenseVoice 语音识别
- **角色**：中文语音转文本 (ASR)，支持多语言、端侧部署的高精度语音识别
- **集成点**：`backend_design/nexus/asr/engine.py` ASR 引擎，模型文件位于 `models/asr/sensevoice/`
- **部署方式**：本地模型推理，通过 modelscope 下载 iic/SenseVoiceSmall 模型
- **关键特性**：多语言支持（中英日韩粤）、低延迟推理、适合车载场景的实时语音识别