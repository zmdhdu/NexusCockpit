/**
 * 根布局组件 — 所有页面共享的外层结构
 *
 * 包含: HTML 骨架、全局样式、侧边栏、主内容区、Sonner Toast 容器
 * Next.js App Router 要求必须有一个根 layout.tsx
 */
import type { Metadata } from "next";
import { Sidebar } from "@/components/layout/sidebar";
import { Toaster } from "sonner";
import "./globals.css";

// 页面元数据 (SEO 用)
export const metadata: Metadata = {
  title: "NexusCockpit — 车载语音 Agent",
  description: "企业级车载语音 Agent 控制台",
};

/**
 * 根布局组件
 * @param children — 子页面内容，由 Next.js 自动注入
 */
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-background antialiased">
        {/* 固定侧边栏 (宽 16rem=256px) */}
        <Sidebar />
        {/* 主内容区，左边距 16rem 避免被侧边栏遮挡 */}
        <main className="ml-64 min-h-screen p-6">{children}</main>
        {/* Sonner Toast 通知容器 — 全局可用 toast.success/error() */}
        <Toaster
          position="top-right"
          theme="dark"
          richColors
          closeButton
        />
      </body>
    </html>
  );
}
