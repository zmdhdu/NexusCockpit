---
kind: frontend_style
name: Next.js + Tailwind CSS 暗色主题设计系统
category: frontend_style
scope:
    - '**'
source_files:
    - frontend_design/tailwind.config.ts
    - frontend_design/src/app/globals.css
    - frontend_design/src/app/layout.tsx
    - frontend_design/src/components/ui/button.tsx
    - frontend_design/src/lib/utils.ts
---

## 样式体系概览

前端采用 Next.js App Router (v14) + Tailwind CSS v3 构建企业级车载语音 Agent 控制台，整体视觉风格为深色系仪表盘（dark dashboard），通过 CSS 变量驱动的设计令牌实现主题一致性。

## 核心架构与工具链

- 框架: Next.js 14.2.5 (App Router)，React 18.3.1
- 样式方案: Tailwind CSS 原子类 + CSS 自定义属性 (CSS Variables) 作为设计令牌层
- 组件库: 自研轻量 UI 组件 (src/components/ui/)，基于 class-variance-authority (CVA) + clsx + tailwind-merge 组合
- 动画: framer-motion 用于页面过渡，Tailwind @keyframes 定义基础动画
- 状态管理: Zustand 全局 store，React Query 服务端数据缓存
- 图表: Recharts 数据可视化
- 3D 座舱: Three.js + React Three Fiber + Drei

## 设计令牌 (Design Tokens)

所有视觉变量集中在 globals.css 的 :root 中，以 HSL 格式定义：

背景: --background, --card, --secondary, --muted, --accent
前景: --foreground, --primary-foreground, --secondary-foreground, --muted-foreground, --destructive-foreground
语义: --primary, --destructive
交互: --input, --border, --ring
尺寸: --radius

这些变量在 tailwind.config.ts 中通过 hsl(var(--xxx)) 映射到 Tailwind 颜色命名空间，形成 bg-primary、text-muted-foreground 等原子类。

## 组件样式约定

按钮 (Button): 使用 CVA 定义变体矩阵，支持 variant (default/secondary/ghost/destructive/outline) × size (sm/md/lg/icon) 组合，所有变体均遵循统一的 focus ring 和 disabled 态。

通用工具:
- cn(...inputs) — 合并类名的标准入口，内部用 clsx 生成字符串 + twMerge 去重冲突类
- 所有组件对外暴露 className prop，允许外部覆盖默认样式

全局效果:
- .glass — 毛玻璃背景 (backdrop-filter blur)
- .glow-primary — 主色发光阴影
- .gradient-text — 渐变文字 (蓝→紫)
- 自定义滚动条样式，宽度 6px，跟随主题色

## 布局与响应式策略

根布局 (layout.tsx) 固定侧边栏宽 16rem (256px)，主内容区通过 ml-64 避让
未引入移动端适配断点，当前为桌面端仪表盘风格
深色模式为唯一主题，无亮色切换逻辑

## 开发规范

1. 颜色使用: 必须通过 var(--xxx) 映射后的 Tailwind 类名，禁止硬编码 RGB/HSL 值
2. 组件样式: 优先使用 CVA 定义变体，复杂样式拆分为独立组件而非内联 style
3. 类名合并: 统一通过 cn() 函数处理，避免手动拼接字符串
4. 动画: 简单动画用 Tailwind animate-*，复杂动作用 framer-motion
5. 字体特性: 启用 font-feature-settings: "rlig" 1, "calt" 1 提升连字渲染