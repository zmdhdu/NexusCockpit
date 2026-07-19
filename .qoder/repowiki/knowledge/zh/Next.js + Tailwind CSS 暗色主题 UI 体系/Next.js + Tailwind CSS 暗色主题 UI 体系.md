---
kind: frontend_style
name: Next.js + Tailwind CSS 暗色主题 UI 体系
category: frontend_style
scope:
    - '**'
source_files:
    - frontend_design/tailwind.config.ts
    - frontend_design/src/app/globals.css
    - frontend_design/src/components/ui/button.tsx
    - frontend_design/src/components/ui/card.tsx
    - frontend_design/src/lib/utils.ts
    - frontend_design/src/app/layout.tsx
    - frontend_design/src/components/layout/sidebar.tsx
    - frontend_design/package.json
---

## 系统概览
前端采用 Next.js 14 App Router + TypeScript，样式体系基于 Tailwind CSS v3，配合 PostCSS/Autoprefixer。整体视觉风格为**深空暗色主题**，通过 CSS 自定义属性（HSL）集中管理设计令牌，组件层使用 `class-variance-authority` + `tailwind-merge` 实现类型安全的变体系统。

## 核心文件与包
- `frontend_design/tailwind.config.ts` — Tailwind 主题扩展：颜色、圆角、动画 keyframes
- `frontend_design/src/app/globals.css` — 全局 CSS 变量（`:root` HSL 令牌）、滚动条、玻璃态/发光/渐变文本等全局效果
- `frontend_design/src/components/ui/` — 原子级 UI 组件（Button/Card/Input/Dialog 等），遵循 shadcn/ui 风格手写实现
- `frontend_design/src/lib/utils.ts` — `cn()` 类名合并工具（clsx + tailwind-merge）
- `frontend_design/package.json` — 依赖清单：zustand、sonner、recharts、framer-motion、three/@react-three/* 等
- `frontend_design/src/app/layout.tsx` — 根布局：固定侧边栏 + 主内容区 + Sonner Toast 容器

## 架构与约定
1. **设计令牌层**：所有颜色以 `hsl(var(--xxx))` 形式在 `globals.css` 的 `:root` 中声明，Tailwind 通过 `theme.extend.colors` 映射到语义化 token（background/foreground/card/primary/secondary/muted/accent/destructive/border/input/ring），支持未来换肤。
2. **组件构建模式**：UI 组件统一使用 `React.forwardRef` + `cn(...)` 合并 className；可复用变体通过 `cva()` 定义（如 Button 的 variant/size），保证类型安全。
3. **页面组织**：按功能域分目录（`app/chat/`、`app/cockpit/`、`app/admin/`…），每个目录一个 `page.tsx`，共享 `layout.tsx` 提供 Sidebar/GPS Provider/Toaster。
4. **动效与特效**：Tailwind 扩展了 `fade-in`、`slide-up`、`pulse-slow` 三类动画；全局提供 `.glass`（毛玻璃）、`.glow-primary`（发光阴影）、`.gradient-text`（渐变色文字）三个通用 class。
5. **图标与交互**：统一使用 `lucide-react` 图标库；Toast 通知通过 `sonner` 在根布局挂载，全局调用 `toast.success()/error()`。
6. **响应式策略**：未引入断点媒体查询，主要依靠 Tailwind 内置响应式前缀（sm/md/lg/xl）和 flex/grid 布局完成适配。

## 开发者规范
- 新增颜色必须先在 `globals.css` 的 `:root` 添加 HSL 变量，再在 `tailwind.config.ts` 的 `theme.extend.colors` 注册语义化 token，禁止直接写死十六进制色值。
- 新建 UI 组件放在 `src/components/ui/`，使用 `forwardRef` + `cn()` + 可选 `cva()` 变体模式，保持与现有 Button/Card 一致。
- 页面级样式尽量用 Tailwind 原子类组合，仅在确实需要时追加 `globals.css` 中的全局 class（glass/glow/gradient-text）。
- 动画优先使用 Tailwind 已定义的 `animate-fade-in` / `animate-slide-up` / `animate-pulse-slow`，新增动画需在 `tailwind.config.ts` 的 `theme.extend.animation` 和 `keyframes` 中成对声明。
- 图标统一从 `lucide-react` 导入，避免内联 SVG。