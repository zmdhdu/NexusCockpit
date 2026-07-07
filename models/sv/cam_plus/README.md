# CAM++ 声纹模型

本目录存放 ModelScope CAM++ 声纹验证模型。

## 下载方式

```bash
modelscope download --model iic/speech_campplus_sv_zh-cn_3dspeaker_16k --local_dir ./
```

## 预期文件

```
cam_plus/
├── campplus_cn_3dspeaker.bin
├── configuration.json
├── README.md
└── ...
```

## 配置

环境变量 `CAM_MODEL_PATH` 默认指向 `./models/sv/cam_plus` (相对路径)。

详见 [SETUP.md](../../docs/deployment/SETUP.md)。
