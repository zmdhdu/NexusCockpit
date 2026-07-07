# Assets 目录

本目录存放项目静态资源文件。

## 子目录

```
assets/
├── speaker/               # 声纹音频文件
│   ├── enroll_wav/        #   注册音频 (enrollment)
│   │   └── enroll_0.wav   #   默认注册音频
│   └── users/             #   用户声纹
│       ├── 主人.wav        #   主人声纹
│       └── 其他.wav        #   其他用户声纹
└── audio/
    └── prompts/           #   音频提示词 (TTS 参考)
```

## 说明

- 声纹音频文件会被 Git 跟踪 (文件较小，属于项目配置)
- 音频提示词目录用于存放 TTS 零样本克隆的参考音频
