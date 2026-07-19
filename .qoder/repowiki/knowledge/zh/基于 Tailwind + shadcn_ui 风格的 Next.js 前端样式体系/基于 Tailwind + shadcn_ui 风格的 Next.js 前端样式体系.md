---
kind: frontend_style
name: 基于 Tailwind + shadcn/ui 风格的 Next.js 前端样式体系
category: frontend_style
scope:
    - '**'
source_files:
    - frontend_design/tailwind.config.ts
    - frontend_design/src/app/globals.css
    - frontend_design/src/app/layout.tsx
    - frontend_design/src/components/ui/button.tsx
    - frontend_design/src/components/ui/card.tsx
    - frontend_design/src/components/ui/input.tsx
    - frontend_design/src/lib/utils.ts
    - frontend_design/src/components/layout/sidebar.tsx
    - frontend_design/src/components/vehicle/vehicle-panel.tsx
    - frontend_design/src/components/chat/chat-window.tsx
    - frontend_design/src/app/page.tsx
    - frontend_design/package.json
---

## 系统与方法论
- 框架与工具链：Next.js 14 App Router + TypeScript + Tailwind CSS 3 + PostCSS + Autoprefixer。
- 设计系统：采用类 shadcn/ui 的原子化组件风格，通过 `class-variance-authority`（CVA）+ `clsx` + `tailwind-merge` 实现类型安全的变体系统与类名合并。图标使用 `lucide-react`，动画使用 `framer-motion`，通知使用 `sonner`，图表使用 `recharts`。
- 主题策略：以 CSS 自定义属性（HSL 值）作为设计令牌，集中定义在根布局的全局样式中，Tailwind 通过 `hsl(var(--xxx))` 引用，天然支持暗色主题。

## 关键文件与包
- 样式配置与全局主题
  - `frontend_design/tailwind.config.ts`：Tailwind 主题扩展、颜色/圆角/动画 keyframes 定义。
  - `frontend_design/src/app/globals.css`：Tailwind 指令注入、`:root` HSL 设计令牌、滚动条/Glass/Glow/渐变文字等全局样式。
  - `frontend_design/src/app/layout.tsx`：应用根布局，挂载 Sidebar、Toaster、GPS Provider 并引入全局样式。
- UI 基础组件（shadcn 风格）
  - `src/components/ui/button.tsx`：基于 CVA 的按钮变体（default/secondary/ghost/destructive/outline × sm/md/lg/icon）。
  - `src/components/ui/card.tsx`：Card/CardHeader/CardTitle/CardDescription/CardContent/CardFooter 组合。
  - `src/components/ui/input.tsx`：统一输入框样式与焦点环。
  - `src/components/ui/dialog.tsx`、`password-change-dialog.tsx`：对话框与密码修改弹窗。
- 业务组件与页面
  - `src/components/layout/sidebar.tsx`：固定侧边栏导航。
  - `src/components/vehicle/*`：车载 3D 模型、车辆面板、语音助手栏等座舱相关 UI。
  - `src/components/chat/chat-window.tsx`、`src/components/voice-recorder.tsx`：聊天窗口与录音控件。
  - `src/app/{cockpit,chat,dashboard,admin,dataplatform,middleware,settings,vehicle}/page.tsx`：按功能划分的页面路由。
- 工具与状态
  - `src/lib/utils.ts`：`cn()` 类名合并、`formatTime()`、`delay()` 等通用函数。
  - `src/stores/auth-store.ts`、`chat-store.ts`：Zustand 轻量状态管理。
  - `src/hooks/use-audio-recorder.ts`、`use-speech-recognition.ts`、`use-gps-location.ts`：语音与 GPS 能力封装。
- 依赖清单
  - `frontend_design/package.json`：声明 next/react/zustand/axios/clsx/tailwind-merge/cva/lucide-react/sonner/recharts/framer-motion/three 等核心依赖。

## 架构与约定
- 目录组织遵循 Next.js App Router 约定：`src/app/<route>/page.tsx` 为页面，`src/components/<domain>/<name>.tsx` 为组件，`src/hooks/`、`src/stores/`、`src/lib/`、`src/types/` 分层清晰。
- 样式方法论：所有视觉样式走 Tailwind utility class，禁止在组件内写内联 style；复杂变体通过 CVA 声明，再通过 `cn(...)` 合并到 className。
- 设计令牌：颜色、圆角、阴影等全部映射到 `:root` 中的 HSL 变量，新增主题只需改一处。
- 动效与反馈：统一使用 framer-motion 做入场/过渡，Sonner 提供 toast 反馈，全局 Toaster 已在 RootLayout 挂载。
- 响应式：未引入额外断点库，完全依赖 Tailwind 内置响应式前缀（sm/md/lg/xl），配合 flex/grid 布局适配。

## 开发者应遵守的规则
1. **优先使用 Tailwind 原子类**，不要新增手写 CSS；如需复用样式，拆成 `src/components/ui/*` 下的基础组件。
2. **主题色一律通过 `bg-*` / `text-*` / `border-*` 等语义化类引用**，不得硬编码十六进制色值；新增颜色需在 `globals.css` 的 `:root` 与 `tailwind.config.ts` 同步扩展。
3. **复杂组件变体用 CVA 声明**，并通过 `cn(buttonVariants({ variant, size }), className)` 合并，保持类型安全与可组合性。
4. **类名冲突统一走 `cn()`**，禁止直接拼接字符串或使用 `||` 条件类，确保 tailwind-merge 能正确去重。
5. **全局效果集中在 `globals.css`**（如 `.glass`、`.glow-primary`、`.gradient-text`、滚动条样式），业务组件只引用这些类名。
6. **图标使用 lucide-react**，避免自行维护 SVG；动画优先使用 framer-motion 或 Tailwind 内置 animation。
7. **页面级布局由 RootLayout 提供**（Sidebar + main 内容区 + Toaster），子页面不应重复包裹外层结构。
8. **新增 UI 组件放入 `src/components/ui/`**，并在 `package.json` 中按需引入依赖，避免在业务组件里直接 import 第三方样式库。