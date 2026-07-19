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
    if (typeof navigator === "undefined" || !navigator.geolocation) return;

    let cancelled = false;

    const fetchLocation = () => {
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
          } catch {
            // 静默失败，后端会降级到 IP 定位
          }
        },
        () => {
          // 用户拒绝或定位失败，静默处理
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
      );
    };

    // 首次获取
    fetchLocation();

    // 降低轮询频率到 5 分钟，仅刷新坐标缓存
    // 逆地理编码 API 不再每次轮询调用
    const interval = setInterval(fetchLocation, 300000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);
}
