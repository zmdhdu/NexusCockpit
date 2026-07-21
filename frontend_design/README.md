# NexusCockpit Web Frontend

> Next.js 14 + TypeScript + Tailwind CSS + Zustand — 企业级车载语音 Agent 前端

## 技术栈

| 技术 | 用途 |
|------|------|
| Next.js 14 (App Router) | React 全栈框架，SSR/SSG 支持 |
| TypeScript | 类型安全 |
| Tailwind CSS | 原子化 CSS 样式 |
| Zustand | 轻量级状态管理 (支持持久化) |
| Three.js | 3D 车型渲染 |
| Recharts | 数据可视化 (雷达图/折线图/仪表盘) |
| Framer Motion | 页面过渡与组件动效 |

## 开发启动

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

## 项目结构

```
src/
├── app/                  # 页面路由 (App Router)
│   ├── cockpit/          #   座舱控制台 (聊天 + 车控 + 3D)
│   ├── chat/             #   独立聊天页面 (SSE 流式)
│   ├── vehicle/          #   车控面板
│   ├── dashboard/        #   仪表盘 HUD
│   ├── settings/         #   设置中心
│   ├── admin/            #   管理后台
│   ├── middleware/        #   中间件监控
│   ├── dataplatform/     #   数据中台
│   ├── layout.tsx        #   全局布局
│   └── page.tsx          #   根路径重定向
├── components/           # 共享组件
│   ├── chat/             #   聊天相关组件
│   ├── layout/           #   布局组件 (侧边栏等)
│   ├── ui/               #   基础 UI 组件
│   ├── vehicle/          #   车控组件 (含 3D 车型)
│   └── voice-recorder.tsx #  语音录制组件
├── hooks/                # 自定义 React Hooks
├── lib/                  # API 客户端与工具函数
├── stores/               # Zustand 状态管理 (含 auth-store)
└── types/                # TypeScript 类型定义
```

## 页面

| 路由 | 说明 |
|------|------|
| `/cockpit` | 座舱控制台 (聊天 + 车控 + 3D 模型联动) |
| `/chat` | 语音助手 (SSE 流式响应、意图标签、Markdown 渲染) |
| `/vehicle` | 车控面板 (空调、车窗、座椅、媒体、导航) |
| `/dashboard` | 仪表盘 HUD (3D 车型 + 实时图表 + 系统总览) |
| `/settings` | 设置 (API 密钥、模型配置、数据库状态) |
| `/admin` | 管理后台 (用户权限、座舱注册) |
| `/middleware` | 中间件监控 (Redis/Milvus/Neo4j/MySQL 状态) |
| `/dataplatform` | 数据中台 (跨座舱统计与分析) |

## 设计风格 (v2.0 HUD 科幻风)

- **HUD 科技风** — 全局深色赛博风、霓虹边框、数据可视化仪表盘
- **3D 车型** — Three.js 渲染车辆 3D 模型，支持旋转/缩放交互 (`vehicle-3d.tsx`)
- **实时图表** — Recharts 数据可视化（雷达图/折线图/仪表盘）
- **动效系统** — Framer Motion 页面过渡 + 组件入场动画
- **玻璃拟态** — `glass` class 实现 backdrop-blur 效果
- **渐变文字** — `gradient-text` class 用于品牌标识
- **发光效果** — `glow-primary` class 用于活跃元素

## 关键组件

| 组件 | 路径 | 功能 |
|------|------|------|
| `vehicle-3d.tsx` | `components/vehicle/` | Three.js 3D 车型渲染 + 车控指令联动 |
| `voice-recorder.tsx` | `components/` | 语音录制与声纹采集 |
| Dashboard HUD | `app/dashboard/page.tsx` | Recharts 实时图表 + 服务状态 + 3D 模型 |
| Settings | `app/settings/page.tsx` | Framer Motion 动效 + API 配置面板 |
