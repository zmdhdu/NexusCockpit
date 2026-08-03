/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 全局 GPS 定位 Hook — 仅获取并缓存浏览器坐标
 *
 * 设计说明:
 *   仅获取 GPS 坐标并存入后端 adapter，
 *   逆地理编码只在用户主动查询位置/周边时按需触发，
 *   避免浪费高德逆地理编码 API 调用量。
 *
 * 增强特性:
 *   - 首次定位失败时自动重试一次（30 秒后）
 *   - 详细的错误日志，便于诊断定位问题
 *   - 成功时打印坐标，确认 GPS 数据已到达后端
 *
 * 使用方式:
 *   在根布局的客户端组件中调用一次即可全局生效。
 *   const {} = useGpsLocation();
 */
"use client";

import { useEffect, useRef } from "react";
import { updateVehicleLocation } from "@/lib/api";
import { useAuth } from "@/stores/auth-store";

export function useGpsLocation() {
  const { cockpitId } = useAuth();
  const cockpitIdRef = useRef(cockpitId);

  // 保持最新的 cockpitId 在 ref 中，避免 effect 频繁重建
  useEffect(() => {
    cockpitIdRef.current = cockpitId;
  }, [cockpitId]);

  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      console.warn("[GPS] 浏览器不支持地理定位 API，将使用 IP 定位降级");
      return;
    }

    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const fetchLocation = (isRetry = false) => {
      navigator.geolocation.getCurrentPosition(
        async (position) => {
          if (cancelled) return;
          try {
            // 仅发送坐标到后端，不触发逆地理编码
            // 后端 /vehicle/location 会存储坐标但不调用 Amap API
            // 逆地理编码在用户查询位置/周边时按需触发
            await updateVehicleLocation(
              position.coords.latitude,
              position.coords.longitude
            );
            console.info(
              `[GPS] 坐标已发送到后端: (${position.coords.latitude.toFixed(4)}, ${position.coords.longitude.toFixed(4)})` +
              `${isRetry ? " (重试成功)" : ""}`
            );
          } catch (err) {
            // 记录错误便于诊断，后端会降级到 IP 定位
            console.error(
              `[GPS] Failed to update vehicle location:`,
              err instanceof Error ? err.message : err
            );
          }
        },
        (err) => {
          if (cancelled) return;

          // 详细的错误日志，便于诊断
          const errorDescriptions: Record<number, string> = {
            1: "用户拒绝了位置权限",
            2: "位置信息不可用（设备未启用 GPS 或信号弱）",
            3: "获取位置超时（10 秒内未获取到）",
          };
          const desc = errorDescriptions[err.code] || `未知错误 (${err.code})`;
          console.warn(`[GPS] Geolocation error: ${desc}`);

          // 首次失败时，30 秒后自动重试一次
          if (!isRetry) {
            console.info("[GPS] 将在 30 秒后自动重试...");
            retryTimer = setTimeout(() => {
              if (!cancelled) {
                fetchLocation(true);
              }
            }, 30000);
          } else {
            console.warn(
              "[GPS] 重试仍失败，后端将使用 IP 定位降级。" +
              "如需精确位置，请检查浏览器定位权限设置。"
            );
          }
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
      );
    };

    // 首次获取
    fetchLocation();

    // 降低轮询频率到 5 分钟，仅刷新坐标缓存
    // 逆地理编码 API 不再每次轮询调用
    const interval = setInterval(() => fetchLocation(false), 300000);

    return () => {
      cancelled = true;
      clearInterval(interval);
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
    };
  }, []);
}
