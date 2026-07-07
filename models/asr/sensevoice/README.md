# SenseVoice ASR 模型

本目录存放 FunASR SenseVoice 语音识别模型。

## 下载方式

```bash
# 使用 ModelScope 下载
modelscope download --model iic/Speech_LLM_Benchmark_ASR --local_dir ./
```

或:

```python
from modelscope.hub.snapshot_download import snapshot_download
snapshot_download(model_id="iic/Speech_LLM_Benchmark_ASR", local_dir=".")
```

## 预期文件

```
sensevoice/
├── model.pt
├── config.yaml
├── am.mvn
├── tokens.txt
└── ...
```

## 配置

环境变量 `FUNASR_MODEL_PATH` 默认指向 `./models/asr/sensevoice` (相对路径)。

详见 [SETUP.md](../../docs/deployment/SETUP.md)。
