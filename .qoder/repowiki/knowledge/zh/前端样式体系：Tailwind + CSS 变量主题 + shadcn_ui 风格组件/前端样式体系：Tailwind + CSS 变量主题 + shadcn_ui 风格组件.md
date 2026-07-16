---
kind: frontend_style
name: 前端样式体系：Tailwind + CSS 变量主题 + shadcn/ui 风格组件
category: frontend_style
scope:
    - '**'
source_files:
    - frontend_design/tailwind.config.ts
    - frontend_design/src/app/globals.css
    - frontend_design/postcss.config.js
    - frontend_design/src/app/layout.tsx
    - frontend_design/src/components/ui/button.tsx
    - frontend_design/src/components/vehicle/voice-assistant-bar.tsx
    - frontend_design/package.json
---

## 1. 系统与方法论
- 构建与运行时：Next.js 14 App Router（frontend_design/），TypeScript 5，PostCSS。
- 样式方案：Tailwind CSS 3 原子类为主，通过 tailwind.config.ts 的 theme.extend 扩展颜色、圆角、动画；全局样式集中在 src/app/globals.css，使用 @layer base/components/utilities 组织。
- 主题机制：基于 CSS 自定义属性（--background、--primary、--radius 等）在 :root 中声明 HSL 值，Tailwind 通过 hsl(var(--xxx)) 引用，实现设计令牌式集中管理。
- 组件库风格：遵循 shadcn/ui 约定——components/ui/* 下用 class-variance-authority + clsx + tailwind-merge 组合出可组合、类型安全的变体组件（如 Button），并通过 cn() 工具合并 className。
- 图标与动效：统一使用 lucide-react 图标；基础动画在 Tailwind 配置中定义（fade-in、slide-up、pulse-slow），业务组件内再叠加 Framer Motion。

## 2. 关键文件与包
- 样式与主题
  - frontend_design/tailwind.config.ts：内容扫描路径、颜色/圆角/动画扩展。
  - frontend_design/src/app/globals.css：Tailwind 指令、:root 设计令牌、滚动条/玻璃态/发光/渐变文本等全局样式。
  - frontend_design/postcss.config.js：启用 tailwindcss 与 autoprefixer。
- UI 基础组件（shadcn 风格）
  - frontend_design/src/components/ui/button.tsx：以 CVA 定义 variant/size 变体的示例。
  - frontend_design/src/components/ui/card.tsx、input.tsx：同类风格的基础控件。
- 布局与页面入口
  - frontend_design/src/app/layout.tsx：根布局，挂载 Sidebar、GpsProvider、Sonner Toaster，并引入 globals.css。
  - frontend_design/src/app/page.tsx 及各功能页（chat/、cockpit/、dashboard/ 等）。
- 业务组件（体现样式用法）
  - frontend_design/src/components/vehicle/voice-assistant-bar.tsx：大量使用 Tailwind 原子类 + 自定义 .glass/.glow-primary/.gradient-text 类，展示暗色座舱风格。
- 依赖清单
  - frontend_design/package.json：核心依赖包括 next、react、tailwindcss、postcss、autoprefixer、class-variance-authority、clsx、tailwind-merge、lucide-react、sonner、framer-motion、recharts、three/@react-three/* 等。

## 3. 架构与约定
- 目录结构按 Next.js App Router 约定：app/ 放路由页面，components/ 分 ui/（通用）、layout/（骨架）、vehicle/（车控域）等业务子目录，hooks/、stores/、lib/、types/ 分层清晰。
- 主题色采用暗色座舱基调：背景/卡片/边框均为深灰蓝调，主色为冷青（--primary），强调色用于交互反馈，所有颜色通过 HSL 变量暴露给 Tailwind，便于后续换肤。
- 组件样式策略：优先使用 Tailwind 原子类表达布局与状态，将复杂变体抽到 CVA 中；跨组件复用的视觉特效（玻璃态、发光、渐变文字）沉淀为全局 CSS 类。
- 响应式与可访问性：通过 Tailwind 断点控制布局；按钮等交互元素使用 focus-visible:ring-* 提供键盘焦点环；字体开启连字特性提升中文渲染质量。
- 动画规范：基础动画在 Tailwind 配置中注册，业务组件通过 animate-* 或 Framer Motion 组合使用，避免散落的 keyframes。

## 4. 开发者应遵守的规则
- 新增颜色/圆角/动画时，统一在 tailwind.config.ts 的 theme.extend 中扩展，不要直接在组件里写死数值。
- 所有视觉令牌必须通过 :root 中的 CSS 变量定义，并在 Tailwind 中以 hsl(var(--xxx)) 引用，禁止硬编码十六进制色值。
- 基础 UI 组件放在 components/ui/，并使用 CVA 定义 variant/size，对外暴露类型化 Props；业务组件只消费这些原子组件。
- 复用型视觉效果（玻璃态、发光、渐变文本等）放入 globals.css 的自定义类，不要在多个组件重复编写相同 CSS。
- 图标统一从 lucide-react 引入，不自行绘制 SVG；动效优先使用 Tailwind 内置动画，必要时在配置中补充 keyframes。
- 页面级布局由 layout.tsx 统一管理（侧边栏、Toaster、GPS Provider），子页面仅关注内容区，避免重复包裹外层容器。
- 样式调试建议：利用 Tailwind 的 hover:/focus:/disabled: 状态修饰符表达交互态，保持单一数据源（CVA variants + Tailwind 类名）。