---
kind: frontend_style
name: 基于 Tailwind + shadcn/ui 风格的原子化主题系统
category: frontend_style
scope:
    - '**'
source_files:
    - frontend_design/tailwind.config.ts
    - frontend_design/src/app/globals.css
    - frontend_design/src/app/layout.tsx
    - frontend_design/src/components/ui/button.tsx
    - frontend_design/postcss.config.js
---

## 1. 体系概览
前端样式采用 Next.js App Router + Tailwind CSS 3 的原子化方案，配合 class-variance-authority（CVA）与 tailwind-merge 实现类型安全的组件变体组合；通过 CSS 变量集中管理设计令牌（颜色、圆角、动画），形成“设计令牌 → Tailwind 扩展 → 组件 CVA 变体”的分层风格体系。

## 2. 核心文件与依赖
- 构建与样式链：`frontend_design/tailwind.config.ts`、`frontend_design/postcss.config.js`、`frontend_design/src/app/globals.css`
- 根布局与全局注入：`frontend_design/src/app/layout.tsx`（挂载 Sidebar、Toaster、GPS Provider 等）
- UI 基础组件（CVA 变体示例）：`frontend_design/src/components/ui/button.tsx`（其余 card/input/dialog/tooltip 等同目录结构）
- 运行时依赖：tailwindcss、class-variance-authority、tailwind-merge、clsx、lucide-react、sonner、framer-motion、recharts、three + @react-three/fiber + @react-three/drei

## 3. 架构与约定
- 设计令牌层：在 `globals.css` 的 `:root` 中定义 HSL 色板（background/foreground/card/primary/secondary/muted/accent/destructive/border/input/ring）及 `--radius`，所有颜色通过 `hsl(var(--xxx))` 引用，便于统一换肤。
- Tailwind 扩展层：`tailwind.config.ts` 将上述 CSS 变量映射到 Tailwind 语义化 token（如 `bg-primary`、`text-muted-foreground`），并扩展自定义动画（fade-in/slide-up/pulse-slow）与圆角尺寸。
- 组件变体层：UI 组件使用 CVA 声明 variant/size 等变体，再通过 `cn(...)` 合并 className，保证变体间可叠加且无冲突。
- 全局样式层：`globals.css` 通过 `@layer base/components/utilities` 组织，提供全局边框、body 字体特性、滚动条美化以及 glass/glow/gradient-text 等通用视觉类。
- 布局约定：`layout.tsx` 作为唯一根布局，固定侧边栏宽度（ml-64）、全局 Toaster（dark 主题、top-right 定位）与 GPS 上下文由 Provider 注入。

## 4. 开发者应遵循的规则
- 颜色与圆角一律通过 Tailwind 语义化 token（`bg-primary`、`rounded-lg` 等）引用，禁止在组件内硬编码十六进制色值。
- 新增视觉 token 时先在 `globals.css` 的 `:root` 补充 CSS 变量，再在 `tailwind.config.ts` 的 theme.extend 中暴露对应 Tailwind 别名。
- 组件样式优先用 CVA 声明变体，并通过 `cn()` 合并外部 className；避免在 JSX 中拼接大量条件 className。
- 全局通用效果（玻璃态、发光、渐变文字等）以 `.glass`、`.glow-primary`、`.gradient-text` 等形式沉淀在 `globals.css`，页面级复用而非重复实现。
- 动画统一走 Tailwind 扩展（`animate-fade-in` / `animate-slide-up` / `animate-pulse-slow`），复杂动效使用 framer-motion 并在组件内局部引入。
- 图标统一使用 lucide-react，保持线性风格一致；Toast 通知通过 sonner 的全局 `<Toaster>` 触发，不自行渲染 DOM。