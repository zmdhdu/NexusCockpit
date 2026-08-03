/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 全局错误边界 — 捕获根 layout.tsx 之外的未处理异常
 *
 * Next.js App Router 约定:
 *   - error.tsx 捕获路由组件内的运行时错误（在 layout 内渲染）
 *   - global-error.tsx 捕获根 layout.tsx 本身的错误（替换整个 <html>/<body>）
 *
 * 此文件必须包含 <html> 和 <body> 标签，因为它替代了根 layout。
 */
"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[GlobalError]", error);
  }, [error]);

  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-background antialiased flex items-center justify-center">
        <div className="flex flex-col items-center gap-6 p-8 text-center">
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-red-500/10">
            <svg
              className="h-10 w-10 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div className="space-y-2">
            <h1 className="text-2xl font-bold text-foreground">
              应用发生严重错误
            </h1>
            <p className="text-sm text-muted-foreground max-w-md">
              页面遇到了未预期的问题。您可以尝试重新加载，如果问题持续请检查后端服务状态。
            </p>
            {error.digest && (
              <p className="text-xs text-muted-foreground/60">
                错误标识: {error.digest}
              </p>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => reset()}
              className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              重试
            </button>
            <button
              onClick={() => window.location.reload()}
              className="rounded-lg border border-border bg-card px-6 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
            >
              刷新页面
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
