---
name: fronted-design
description: 当需要设计或实现高质量前端页面/组件（Web UI、美化、落地页、控制台）时使用。覆盖 Next.js App Router、Tailwind CSS、Zustand、SSE 流式、组件设计等 NexusCockpit 前端技术栈。
---

## 权威入口

- `.catpaw/skills/fronted-design/SKILL.md`

## 适用场景

- 从需求到页面落地的 UI 实现任务（新建页面/组件）。
- 需要提升现有界面的视觉层级与一致性。
- 需要在不改业务逻辑前提下优化体验（动画、空态、错误态）。
- 需要实现 SSE 流式聊天、WebSocket 实时通信等前端交互。
- 需要设计 Zustand 状态管理方案（多座舱切换、持久化）。
- 需要封装自定义 Hooks（语音识别、异步请求、GPS 定位等）。

## 非适用场景

- 不用于替代业务接口设计或数据库建模（使用 `rapid-dev`）。
- 不用于无依据的大改风格（需与品牌/产品目标一致）。
- 不用于后端代码开发。
- 不用于代码质量审查（使用 `code-review`）。

## NexusCockpit 前端技术栈

| 技术 | 版本 | 用途 | 在项目中的位置 |
|------|------|------|----------------|
| Next.js | 14+ (App Router) | React 全栈框架 | `frontend_design/src/app/` |
| TypeScript | 5+ | 类型安全 | 全局 |
| Tailwind CSS | 3+ | 原子化 CSS | `tailwind.config.ts` |
| Zustand | 4+ | 全局状态管理 | `src/stores/` |
| clsx + tailwind-merge | - | 类名合并 | `src/lib/utils.ts` → `cn()` |
| sonner | - | Toast 通知 | `src/app/layout.tsx` → `<Toaster />` |
| lucide-react | - | 图标库 | 各组件 |
| react-markdown + remark-gfm | - | Markdown 渲染 | `chat-window.tsx` |
| native fetch + ReadableStream | - | SSE 流式读取 | `src/lib/api.ts` → `streamMessage()` |
| AbortController | - | 请求取消 | `chat-window.tsx` → `handleStop()` |
| Web Speech API | - | 浏览器 TTS | `src/lib/tts.ts` |
| SpeechRecognition API | - | 浏览器语音识别 | `src/hooks/use-speech-recognition.ts` |

## 执行步骤

### 1. 明确页面目标
- 核心用户任务是什么？（如：聊天对话、车控操作、数据监控）
- 成功标准是什么？（如：SSE 流式无卡顿、车控指令 < 200ms 响应）
- 哪些页面路由？（`/cockpit`、`/chat`、`/dashboard`、`/middleware` 等）

### 2. 设计结构层级
- 布局：是否需要 Sidebar？是否全屏？
- 信息密度：卡片网格 vs 列表流 vs 分栏
- 主要操作路径：用户从进入到完成任务经过几步？

### 3. 定义视觉规则
- 颜色：遵循座舱主题色（`#4fc3f7`/`#66bb6a`/`#ab47bc`）
- 字体：系统默认 + Tailwind `text-sm`/`text-base`/`text-lg`
- 间距：Tailwind 间距系统（`gap-2`/`gap-4`/`p-4`/`p-6`）
- 状态反馈：loading 骨架屏、empty 空态图、error 错误提示

### 4. 补全交互细节
- hover: 卡片悬停边框高亮
- focus: 输入框聚焦边框
- loading: 骨架屏 / Spinner
- empty: 空态插画 + 引导文案
- error: sonner toast 错误提示

### 5. 交付前检查
- 响应式：移动端 / 平板 / 桌面
- 可访问性：aria-label、keyboard navigation
- 性能：组件懒加载、图片优化、避免不必要的 re-render

## NexusCockpit 前端设计规范

### 页面路由结构

```
src/app/
├── layout.tsx              # 根布局（Sidebar + Toaster + GpsProvider）
├── page.tsx                # 首页（重定向到 /cockpit）
├── cockpit/                # 座舱控制页（聊天 + 车控 + 3D）
├── chat/                   # 独立聊天页
├── dashboard/              # 运营总览（图表 + 统计）
├── vehicle/                # 独立车控页
├── dataplatform/           # 数据中台
├── middleware/             # 中间件看板
├── settings/               # 设置中心
└── admin/                  # 管理后台（RBAC）
```

### 组件设计模式

#### 1. 页面组件模式
```tsx
"use client"
import { useState, useEffect } from "react"
import { useAuth } from "@/stores/auth-store"

export default function SomePage() {
  const { token, cockpitId } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function fetchData() {
      try {
        const res = await api.get(`/some-endpoint/${cockpitId}`)
        if (!cancelled) setData(res.data)
      } catch (err) {
        if (!cancelled) toast.error("加载失败")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchData()
    return () => { cancelled = true }
  }, [cockpitId])

  if (loading) return <Skeleton />
  return <div>{/* content */}</div>
}
```

#### 2. SSE 流式聊天模式
```tsx
async function handleStreamMessage(
  text: string,
  onChunk: (content: string) => void,
  onDone: () => void
) {
  const controller = new AbortController()
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message: text, cockpit_id: cockpitId }),
    signal: controller.signal,
  })

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() || ""
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6)
        if (data === "[DONE]") { onDone(); return }
        onChunk(JSON.parse(data).content)
      }
    }
  }
}
```

#### 3. Zustand Store 模式
```tsx
import { create } from "zustand"
import { persist } from "zustand/middleware"

interface SomeState {
  data: SomeType[]
  loading: boolean
  setData: (data: SomeType[]) => void
  reset: () => void
}

export const useSomeStore = create<SomeState>()(
  persist(
    (set) => ({
      data: [],
      loading: false,
      setData: (data) => set({ data }),
      reset: () => set({ data: [], loading: false }),
    }),
    { name: "some-storage" }
  )
)
```

### 类名合并规范
```tsx
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// 使用: <div className={cn("p-4 bg-white", isActive && "bg-blue-50", className)} />
```

### 座舱主题色切换
```tsx
const COCKPIT_THEMES: Record<string, string> = {
  "cockpit-01": "#4fc3f7",  // 蓝色
  "cockpit-02": "#66bb6a",  // 绿色
  "cockpit-03": "#ab47bc",  // 紫色
}

function CockpitHeader({ cockpitId }: { cockpitId: string }) {
  const themeColor = COCKPIT_THEMES[cockpitId] || "#4fc3f7"
  return (
    <div style={{ borderColor: themeColor }}>
      <h2 style={{ color: themeColor }}>{cockpitId}</h2>
    </div>
  )
}
```

## 常见陷阱

- 只改样式不改信息层级，导致可用性仍差。
- 动效过多影响主任务与页面性能（Framer Motion 需节制使用）。
- 忽略空态与错误态，导致体验断层。
- SSE 流式请求未使用 AbortController，切换对话时旧请求继续推送。
- Zustand store 未在座舱切换时清空，导致跨座舱数据泄漏。
- useEffect 未加 cancelled 标志位，组件卸载后仍 setState 导致内存泄漏。
- 直接使用 `fetch` 而非项目封装的 `api` 实例，导致 JWT Token 未自动附加。
