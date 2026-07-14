/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 通用工具函数 — 前端各组件共用的辅助方法
 *
 * 包含: CSS 类名合并、时间格式化、延时等待
 */
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * 合并 CSS 类名 — 解决 Tailwind CSS 类冲突问题
 *
 * 工作原理:
 *   1. clsx() 将各种格式的类名（字符串/数组/对象）合并为单个字符串
 *   2. twMerge() 检测并移除 Tailwind 冲突类（如 "px-2 px-4" → "px-4"）
 *
 * @example
 *   cn("px-2 py-1", condition && "bg-blue-500", { "text-white": isActive })
 *   // → "px-2 py-1 bg-blue-500 text-white"
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * 格式化时间为 "时:分" 格式 — 用于聊天消息时间戳显示
 *
 * @param date - Date 对象或 ISO 时间字符串
 * @returns 如 "14:30" 的简短时间字符串
 */
export function formatTime(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * 延时等待 — 返回一个在指定毫秒后 resolve 的 Promise
 *
 * 用于在异步流程中插入等待（如轮询间隔、动画延迟等）。
 *
 * @param ms - 等待的毫秒数
 * @example
 *   await delay(500); // 等待 500ms 后继续执行
 */
export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
