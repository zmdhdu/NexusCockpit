# NexusCockpit Web Frontend

> Next.js 14 + TailwindCSS + shadcn/ui 风格组件

## 启动

```bash
cd frontend_design

# 安装依赖
npm install

# 复制环境变量
cp .env.local.example .env.local

# 开发模式
npm run dev

# 构建
npm run build && npm start
```

## 页面

| 路由 | 说明 |
|------|------|
| `/dashboard` | 仪表盘 (系统总览、服务状态、缓存统计) |
| `/chat` | 语音助手 (文本对话、流式响应) |
| `/vehicle` | 车控面板 (空调、车窗、座椅、媒体、导航) |
| `/settings` | 设置 (API 密钥、模型配置、数据库状态) |

## 设计

- **暗色主题** — 车载场景适合暗色 UI
- **玻璃拟态** — `glass` class 实现 backdrop-blur 效果
- **渐变文字** — `gradient-text` class 用于品牌标识
- **发光效果** — `glow-primary` class 用于活跃元素
