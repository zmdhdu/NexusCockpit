---
kind: external_dependency
name: CosyVoice 语音合成
slug: cosyvoice
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### CosyVoice 语音合成
- **角色**: 高质量中文语音合成引擎，支持声音克隆和个性化服务
- **集成点**: `backend_design/nexus/tts/engine.py` TTS 引擎封装
- **模型配置**: ./models/tts/cosyvoice 目录，约 3.5GB 模型文件
- **关键特性**: 高质量语音合成、声音克隆、情感控制
- **部署模式**: 本地模型推理，与声纹识别结合实现个性化语音