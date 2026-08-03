/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 路由级错误边界 — 捕获页面组件渲染时的未处理异常
 *
 * Next.js App Router 约定:
 *   - error.tsx 放在 app/ 目录下，捕获所有路由页面的运行时错误
 *   - 它在根 layout 内渲染，因此保留了侧边栏等共享 UI
 *   - 必须是 "use client" 组件
 *
 * 当 React 组件渲染时抛出未捕获异常（如 data.xxx 访问 undefined 属性），
 * 此组件会替代出错页面内容，提供友好的错误提示和恢复操作。
 */
"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw, Home } from "lucide-react";
import { useRouter } from "next/navigation";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();

  useEffect(() => {
    console.error("[RouteError]", error);
  }, [error]);

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-amber-500/10">
        <AlertTriangle className="h-10 w-10 text-amber-500" />
      </div>
      <div className="space-y-2">
        <h2 className="text-xl font-semibold text-foreground">
          页面加载出错
        </h2>
        <p className="text-sm text-muted-foreground max-w-md">
          {error.message || "渲染过程中发生了未预期的错误。您可以重试或返回首页。"}
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
          className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <RotateCcw className="h-4 w-4" />
          重试
        </button>
        <button
          onClick={() => router.push("/")}
          className="flex items-center gap-2 rounded-lg border border-border bg-card px-5 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          <Home className="h-4 w-4" />
          返回首页
        </button>
      </div>
    </div>
  );
}
