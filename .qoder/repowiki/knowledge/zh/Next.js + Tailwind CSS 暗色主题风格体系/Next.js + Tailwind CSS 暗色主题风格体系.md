---
kind: frontend_style
name: Next.js + Tailwind CSS 暗色主题风格体系
category: frontend_style
scope:
    - '**'
source_files:
    - frontend_design/tailwind.config.ts
    - frontend_design/src/app/globals.css
    - frontend_design/postcss.config.js
    - frontend_design/package.json
    - frontend_design/src/components/ui/button.tsx
    - frontend_design/src/app/layout.tsx
    - frontend_design/src/components/vehicle/voice-assistant-bar.tsx
---

## 1. 技术栈与工具链
- 框架：Next.js 14 App Router（`frontend_design/src/app/*`）
- 样式方案：Tailwind CSS 3 + PostCSS + Autoprefixer，通过 `tailwind.config.ts` 扩展主题。
- 原子类 + 设计令牌：所有颜色、圆角等通过 CSS 变量（`--background`、`--primary` 等 HSL 值）在 `globals.css` 的 `:root` 中集中声明，Tailwind 以 `hsl(var(--xxx))` 引用，实现统一换肤。
- 组件库：自研轻量 UI 层位于 `src/components/ui/`，基于 `class-variance-authority` + `clsx` + `tailwind-merge` 提供类型安全的变体系统（如 Button 的 variant/size）。图标使用 `lucide-react`。
- 动画与动效：`framer-motion` 用于复杂交互，Tailwind 自定义 keyframes（`fadeIn`、`slideUp`、`pulse-slow`）处理简单过渡。
- 状态管理：Zustand（`src/stores/*`），UI 层无第三方 UI 框架依赖。
- 构建产物：PostCSS 仅挂载 tailwindcss 与 autoprefixer，无 Sass/Less。

## 2. 关键文件与包
- `frontend_design/tailwind.config.ts` — 主题扩展、颜色映射、动画 keyframes。
- `frontend_design/src/app/globals.css` — Tailwind 指令注入、`:root` 设计令牌、全局滚动条/玻璃态/发光/渐变文本等基础样式。
- `frontend_design/postcss.config.js` — PostCSS 插件配置。
- `frontend_design/package.json` — Next/Tailwind/CVA/lucide-react/framer-motion/recharts/three 等前端依赖清单。
- `frontend_design/src/components/ui/button.tsx` — CVA 变体系统的代表实现，展示 variant/size 组合模式。
- `frontend_design/src/app/layout.tsx` — 根布局，注入全局 Sidebar、Toaster、GPS Provider，并设置 `bg-background antialiased` 等基础 body 样式。
- `frontend_design/src/components/vehicle/voice-assistant-bar.tsx` — 典型业务组件，集中体现 glass/cn/cva 等风格约定。

## 3. 架构与约定
- 目录组织遵循 Next.js App Router：页面在 `src/app/<route>/page.tsx`，共享布局在 `layout.tsx`；可复用 UI 放在 `src/components/ui`，业务组件按领域分目录（chat、layout、vehicle）。
- 设计令牌分层：`globals.css` 定义语义化 CSS 变量 → Tailwind theme.extend.colors 映射到 `hsl(var(--xxx))` → 组件直接使用 `bg-primary`、`text-muted-foreground` 等原子类，避免硬编码颜色。
- 组件变体规范：所有可复用的 UI 组件通过 `cva(...)` 声明 variants（variant/size 等），并通过 `cn(buttonVariants({ variant, size }), className)` 合并外部 class，保证可扩展且类型安全。
- 视觉风格：默认暗色主题（背景 `hsl(222 47% 11%)`，主色 `hsl(199 89% 48%)` 天蓝），配合 `.glass`（毛玻璃）、`.glow-primary`（外发光）、`.gradient-text`（渐变色文字）等全局辅助类营造科技感仪表盘风格。
- 响应式策略：完全基于 Tailwind 断点原子类（如 `md:`、`lg:`），未引入独立媒体查询或 CSS-in-JS 方案。
- 动画约定：简单过渡用 Tailwind 内置 transition + 自定义 keyframes；复杂入场/手势用 framer-motion。

## 4. 开发者应遵守的规则
1. **颜色一律走设计令牌**：禁止在组件中写死十六进制颜色，优先使用 `bg-primary`、`text-muted-foreground` 等语义化 Tailwind 类；新增颜色先在 `globals.css` 的 `:root` 加变量，再在 `tailwind.config.ts` 的 colors 中映射。
2. **可复用 UI 必须用 CVA**：新建按钮、卡片、输入框等通用组件时，使用 `class-variance-authority` 声明 variants，并通过 `cn()` 合并 className，保持 API 一致。
3. **样式来源优先级**：Tailwind 原子类 > 组件内 cva 变体 > `globals.css` 中的 `@layer base/components/utilities` 自定义规则，避免手写冲突样式。
4. **动画选择**：优先使用 Tailwind 的 `animate-*` 和自定义 keyframes；需要复杂时序/手势时才引入 framer-motion。
5. **图标与资源**：统一通过 `lucide-react` 导入 SVG 图标，不直接引用图片路径作为装饰元素。
6. **布局结构**：页面级布局由 `layout.tsx` 的 Sidebar + main 容器决定，子页面只关注内容区，不要重复包裹外层布局。