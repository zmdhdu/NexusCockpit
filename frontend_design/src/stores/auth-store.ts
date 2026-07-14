/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 认证状态管理 — v2.1 RBAC + 座舱选择
 *
 * 从 JWT Token 中解析用户角色和座舱 ID，
 * 提供全局认证状态和座舱切换能力。
 *
 * RBAC 角色层级:
 *   super_admin   → 所有功能（注册/删除座舱、管理用户、数据中台、中间件、设置）
 *   cockpit_admin → 座舱管理 + 对话/车控 + 数据中台 + 中间件
 *   cockpit_user  → 对话/车控 + 仪表盘
 *   cockpit_viewer → 只读仪表盘
 */
"use client";

import { useState, useEffect, useCallback } from "react";
import type { UserRole } from "@/types";

const TOKEN_KEY = "nexus_token";
const COCKPIT_KEY = "nexus_cockpit_id";

/** JWT Token payload 结构 */
interface JWTPayload {
  sub: string;          // user_id
  cockpit_id?: string;  // 座舱 ID
  role?: string;        // 用户角色
  exp?: number;         // 过期时间
  auth_method?: string; // 认证方式
}

/** 认证状态 */
interface AuthState {
  token: string | null;
  userId: string;
  role: UserRole;
  cockpitId: string;
  isAuthenticated: boolean;
}

/** 默认认证状态（未登录） */
const defaultAuthState: AuthState = {
  token: null,
  userId: "",
  role: "cockpit_user",
  cockpitId: "cockpit-01",
  isAuthenticated: false,
};

/** 全局认证状态（模块级单例） */
let _authState: AuthState = { ...defaultAuthState };
const _listeners = new Set<() => void>();

/** 解析 JWT Token 的 payload */
function parseToken(token: string): JWTPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]));
    return payload;
  } catch {
    return null;
  }
}

/** 从 localStorage 加载并解析 Token */
function loadAuthFromStorage(): AuthState {
  if (typeof window === "undefined") return { ...defaultAuthState };

  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return { ...defaultAuthState };

  const payload = parseToken(token);
  if (!payload) return { ...defaultAuthState };

  // 检查是否过期
  if (payload.exp && Date.now() >= payload.exp * 1000) {
    localStorage.removeItem(TOKEN_KEY);
    return { ...defaultAuthState };
  }

  // 从 localStorage 获取上次选择的座舱，如果没有则使用 Token 中的或默认值
  const savedCockpitId = localStorage.getItem(COCKPIT_KEY) || payload.cockpit_id || "cockpit-01";
  // 确保 cockpit_id 始终写入 localStorage，供 API 拦截器使用
  localStorage.setItem(COCKPIT_KEY, savedCockpitId);

  return {
    token,
    userId: payload.sub || "",
    role: (payload.role as UserRole) || "cockpit_user",
    cockpitId: savedCockpitId,
    isAuthenticated: true,
  };
}

/** 通知所有监听器状态已更新 */
function notifyListeners() {
  _listeners.forEach((fn) => fn());
}

/** 设置认证 Token（登录/声纹验证后调用） */
export function setAuthToken(token: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(TOKEN_KEY, token);
    _authState = loadAuthFromStorage();
    notifyListeners();
  }
}

/** 设置当前座舱 ID */
export function setCockpitId(cockpitId: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(COCKPIT_KEY, cockpitId);
    _authState = { ..._authState, cockpitId };
    notifyListeners();
  }
}

/** 清除认证状态（登出） */
export function clearAuth() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    _authState = { ...defaultAuthState };
    notifyListeners();
  }
}

/** 获取当前认证状态 */
export function getAuthState(): AuthState {
  return _authState;
}

/**
 * React Hook: 使用认证状态
 *
 * 在组件中调用此 hook 获取当前用户角色、座舱 ID 等信息，
 * 状态变化时自动触发组件重渲染。
 */
export function useAuth(): AuthState & {
  setToken: (token: string) => void;
  switchCockpit: (cockpitId: string) => void;
  logout: () => void;
} {
  const [state, setState] = useState<AuthState>(_authState);

  useEffect(() => {
    // 首次加载时从 localStorage 读取
    _authState = loadAuthFromStorage();
    setState(_authState);

    // 订阅状态变化
    const listener = () => setState({ ..._authState });
    _listeners.add(listener);

    // 定时检查 Token 是否过期
    const interval = setInterval(() => {
      const newState = loadAuthFromStorage();
      if (newState.isAuthenticated !== _authState.isAuthenticated) {
        _authState = newState;
        notifyListeners();
      }
    }, 60000); // 每分钟检查一次

    return () => {
      _listeners.delete(listener);
      clearInterval(interval);
    };
  }, []);

  return {
    ...state,
    setToken: setAuthToken,
    switchCockpit: setCockpitId,
    logout: clearAuth,
  };
}

// ============================================================
// RBAC 权限检查工具函数
// ============================================================

/** 角色权限层级数字（越大权限越高） */
const ROLE_LEVEL: Record<UserRole, number> = {
  cockpit_viewer: 0,
  cockpit_user: 1,
  cockpit_admin: 2,
  super_admin: 3,
};

/** 检查用户是否有权限访问指定角色级别的功能 */
export function hasRole(userRole: UserRole, requiredRole: UserRole): boolean {
  return ROLE_LEVEL[userRole] >= ROLE_LEVEL[requiredRole];
}

/** 检查用户是否可以查看数据中台 */
export function canViewDataPlatform(role: UserRole): boolean {
  return hasRole(role, "cockpit_admin");
}

/** 检查用户是否可以查看中间件状态 */
export function canViewMiddleware(role: UserRole): boolean {
  return hasRole(role, "cockpit_admin");
}

/** 检查用户是否可以访问设置中心 */
export function canAccessSettings(role: UserRole): boolean {
  return hasRole(role, "cockpit_admin");
}

/** 检查用户是否可以注册/删除座舱 */
export function canManageCockpits(role: UserRole): boolean {
  return role === "super_admin";
}

/** 检查用户是否可以管理用户 */
export function canManageUsers(role: UserRole): boolean {
  return hasRole(role, "cockpit_admin");
}
