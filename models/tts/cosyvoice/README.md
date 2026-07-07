# CosyVoice TTS 模型

本目录存放 CosyVoice 语音合成模型。

## 下载方式

```bash
modelscope download --model iic/CosyVoice-300M --local_dir ./
```

> 模型文件较大 (约 3.5GB)，请确保磁盘空间充足。

## 预期文件

```
cosyvoice/
├── llm.pt
├── flow.pt
├── hift.pt
├── spk2info.pt
├── campplus.onnx
├── speech_tokenizer_v1.onnx
├── cosyvoice.yaml
├── configuration.json
└── ...
```

## 配置

环境变量 `COSYVOICE_MODEL_PATH` 默认指向 `./models/tts/cosyvoice` (相对路径)。

详见 [SETUP.md](../../docs/deployment/SETUP.md)。
