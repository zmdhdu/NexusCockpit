---
kind: frontend_style
name: Next.js + Tailwind CSS 暗色主题前端样式体系
category: frontend_style
scope:
    - '**'
source_files:
    - frontend_design/tailwind.config.ts
    - frontend_design/src/app/globals.css
    - frontend_design/postcss.config.js
    - frontend_design/src/app/layout.tsx
    - frontend_design/src/components/ui/button.tsx
    - frontend_design/src/lib/utils.ts
    - frontend_design/package.json
---

NexusCockpit 前端基于 Next.js 14 App Router 构建，采用 Tailwind CSS 3.x 作为核心样式框架，配合 PostCSS 与 Autoprefixer 完成样式编译。整体风格为深色系车载座舱 UI，通过 CSS 变量定义设计令牌（Design Tokens），实现主题一致性与可维护性。

**样式系统与工具链**
- 样式框架：Tailwind CSS 3.4.4，通过 `postcss.config.js` 启用 tailwindcss 与 autoprefixer。
- 全局样式入口：`src/app/globals.css`，使用 `@tailwind base/components/utilities` 指令引入 Tailwind 层，并在 `:root` 中定义全部设计令牌（background、foreground、primary、secondary、muted、accent、destructive、border、input、ring 等 HSL 值）。
- 类名合并工具：`src/lib/utils.ts` 提供 `cn()` 函数，组合 `clsx` 与 `tailwind-merge`，用于安全合并冲突的 Tailwind 类名。
- 动画系统：在 `tailwind.config.ts` 中扩展了 `fade-in`、`slide-up`、`pulse-slow` 三类自定义动画及对应 keyframes。

**设计令牌与主题策略**
- 所有颜色通过 CSS 变量（如 `--background: 222 47% 11%`）声明，Tailwind 配置中使用 `hsl(var(--xxx))` 引用，形成单一主题源。
- 圆角统一由 `--radius: 0.5rem` 控制，并通过 `lg/md/sm` 三级变体派生。
- 深色主题为主色调，强调色 `--primary` 使用高饱和度青蓝色（199 89% 48%），符合车载暗色驾驶场景。

**组件库与原子化样式**
- 基础 UI 组件位于 `src/components/ui/`，包括 button、card、dialog、input、tooltip、password-change-dialog 等。
- 按钮组件 `button.tsx` 使用 `class-variance-authority` (cva) 定义 variant（default/secondary/ghost/destructive/outline）与 size（sm/md/lg/icon）变体，结合 `cn()` 生成类型安全的样式组合。
- 业务组件按功能域组织：`chat/`（对话窗口与 TTS 控制）、`layout/`（侧边栏与 GPS 提供者）、`vehicle/`（3D 车辆模型与面板）、`voice-recorder.tsx`（语音录制）。

**全局布局与视觉增强**
- 根布局 `layout.tsx` 固定侧边栏（宽 16rem），主内容区左偏移避免遮挡，全局注入 Sonner Toast 通知容器。
- 自定义全局样式：`globals.css` 中包含自定义滚动条（6px 宽度，跟随主题色）、`.glass` 毛玻璃效果、`.glow-primary` 发光阴影、`.gradient-text` 渐变色文字等视觉增强类。

**状态管理与交互**
- 全局状态使用 Zustand（`stores/auth-store.ts`、`stores/chat-store.ts`），与样式层解耦。
- 动画与过渡依赖 `framer-motion`，3D 可视化使用 `three` + `@react-three/fiber` + `@react-three/drei`。
- 图表展示使用 `recharts`，Markdown 渲染使用 `react-markdown` + `remark-gfm`。

**约束与约定**
- 所有新组件应优先复用 `src/components/ui/` 中的原子组件，通过 cva 定义变体。
- 颜色必须通过 CSS 变量引用，禁止硬编码十六进制颜色值（除 `.gradient-text` 等少数渐变特例）。
- 类名冲突统一通过 `cn()` 工具处理，禁止直接使用字符串拼接方式合并 Tailwind 类。
- 动画时长统一控制在 0.3s 以内，保持车载场景下的流畅响应。