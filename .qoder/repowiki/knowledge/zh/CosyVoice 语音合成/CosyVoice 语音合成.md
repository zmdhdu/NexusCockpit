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
- **角色**：高质量文本转语音 (TTS)，支持声音克隆和个性化语音服务
- **集成点**：`backend_design/nexus/tts/engine.py` TTS 引擎，模型文件位于 `models/tts/cosyvoice/`
- **部署方式**：本地模型推理，通过 modelscope 下载 iic/CosyVoice-300M 模型（约 3.5GB）
- **关键特性**：高质量语音合成、声音克隆能力、与声纹识别系统集成实现个性化语音