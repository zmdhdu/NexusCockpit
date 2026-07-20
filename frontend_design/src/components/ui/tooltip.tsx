/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 轻量级 Tooltip 组件 — 纯 CSS 实现，无外部依赖
 *
 * 使用 Tailwind 的 group / group-hover 实现鼠标悬停显示提示文字。
 * 支持 top / bottom / left / right 四个方向。
 *
 * 用法:
 *   <Tooltip content="调低温度">
 *     <Button>...</Button>
 *   </Tooltip>
 */

import * as React from "react";
import { cn } from "@/lib/utils";

type TooltipSide = "top" | "bottom" | "left" | "right";

interface TooltipProps {
  /** 提示文字 */
  content: string;
  /** 提示方向，默认 top */
  side?: TooltipSide;
  /** 子元素 */
  children: React.ReactNode;
  /** 额外 className */
  className?: string;
}

/** 不同方向的定位样式 */
const SIDE_CLASSES: Record<TooltipSide, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2",
};

export function Tooltip({ content, side = "top", children, className }: TooltipProps) {
  if (!content) return <>{children}</>;

  return (
    <span className={cn("group relative inline-block", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 whitespace-nowrap rounded-md border border-border",
          "bg-card/95 px-2.5 py-1.5 text-xs text-card-foreground shadow-md",
          "opacity-0 scale-95 transition-all duration-150",
          "group-hover:opacity-100 group-hover:scale-100",
          "group-focus-visible:opacity-100 group-focus-visible:scale-100",
          SIDE_CLASSES[side]
        )}
      >
        {content}
      </span>
    </span>
  );
}
