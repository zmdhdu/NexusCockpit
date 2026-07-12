"use client";

import { useGpsLocation } from "@/hooks/use-gps-location";

/**
 * GPS 定位提供者 — 在根布局中挂载，确保所有页面都持续更新位置
 *
 * 这是一个不渲染任何 UI 的透明组件，
 * 仅在挂载时启动 GPS 定位轮询。
 */
export function GpsProvider({ children }: { children: React.ReactNode }) {
  useGpsLocation();
  return <>{children}</>;
}
