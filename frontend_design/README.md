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
| `/dashboard` | 仪表盘 (v2.0 HUD: 3D 车型 + 实时图表 + 系统总览) |
| `/chat` | 语音助手 (文本对话、流式响应、意图标签) |
| `/vehicle` | 车控面板 (空调、车窗、座椅、媒体、导航) |
| `/settings` | 设置 (API 密钥、模型配置、数据库状态) |

## 设计 (v2.0 HUD 科幻风)

- **HUD 科技风** — 全局深色赛博风、霓虹边框、数据可视化仪表盘
- **3D 车型** — Three.js 渲染车辆 3D 模型，支持旋转/缩放交互 (`vehicle-3d.tsx`)
- **实时图表** — Recharts 数据可视化（雷达图/折线图/仪表盘）
- **动效系统** — Framer Motion 页面过渡 + 组件入场动画
- **玻璃拟态** — `glass` class 实现 backdrop-blur 效果
- **渐变文字** — `gradient-text` class 用于品牌标识
- **发光效果** — `glow-primary` class 用于活跃元素

## 关键组件 (v2.0)

| 组件 | 路径 | 功能 |
|------|------|------|
| `vehicle-3d.tsx` | `components/vehicle/` | Three.js 3D 车型渲染 + 车控指令联动 |
| Dashboard HUD | `app/dashboard/page.tsx` | Recharts 实时图表 + 服务状态 + 3D 模型 |
| Settings | `app/settings/page.tsx` | Framer Motion 动效 + API 配置面板 |
