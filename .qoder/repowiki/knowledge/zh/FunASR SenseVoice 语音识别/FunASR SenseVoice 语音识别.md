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
- **角色**: 中文语音转文本引擎，支持多语言识别和端侧部署
- **集成点**: `backend_design/nexus/asr/engine.py` ASR 引擎封装
- **模型配置**: ./models/asr/sensevoice 目录，需通过 modelscope 下载
- **关键特性**: 多语言支持（中英日韩粤）、实时识别、低延迟
- **部署模式**: 本地模型推理，无需外部 API 依赖