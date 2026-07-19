/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 侧边栏组件 — 以用户视角设计的导航
 *
 * 会话管理:
 *   - 语音助手菜单下方显示会话列表（类似豆包/ChatGPT）
 *   - 新建对话按钮
 *   - 切换会话
 *   - 删除会话
 *
 * 设计原则:
 *   1. 不展示技术名词（SubAgent、MainAgent、RBAC 等对用户不可见）
 *   2. 按角色分区: 普通用户看到"座舱控制、语音助手、个人设置"
 *      管理员额外看到"运营总览、系统监控、管理设置"
 *   3. 管理员也能访问用户功能（测试/巡检用）
 */
"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Car,
  MessageSquare,
  Settings,
  Activity,
  BarChart3,
  Server,
  ChevronDown,
  User,
  ShieldCheck,
  LogOut,
  Plus,
  Trash2,
  MessageCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getHealth, getCockpits, logout as apiLogout, listChatSessions, createChatSession, deleteChatSession } from "@/lib/api";
import {
  useAuth,
  canViewDataPlatform,
  canViewMiddleware,
  canAccessSettings,
} from "@/stores/auth-store";
import { useChatStore, type SessionMeta } from "@/stores/chat-store";
import type { Cockpit } from "@/types";

/** 导航菜单项 */
interface NavItem {
  href: string;
  label: string;
  icon: typeof Car;
}

/** 用户功能菜单 — 所有角色可见 */
const userNavItems: NavItem[] = [
  { href: "/cockpit", label: "座舱控制", icon: Car },
  { href: "/chat", label: "语音助手", icon: MessageSquare },
  { href: "/settings", label: "个人设置", icon: Settings },
];

/** 管理功能菜单 — 仅管理员可见 */
const adminNavItems: NavItem[] = [
  { href: "/dashboard", label: "运营总览", icon: BarChart3 },
  { href: "/middleware", label: "系统监控", icon: Server },
  { href: "/admin", label: "管理设置", icon: ShieldCheck },
];

/** 侧边栏组件 */
export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { role, cockpitId, switchCockpit, userId, isAuthenticated, logout: authLogout } = useAuth();
  const {
    setCockpitId: setCockpitIdInChat,
    sessionId,
    setSessionId,
    newSession,
    setSessions,
    removeSession,
    sessionsByCockpit,
    userId: chatUserId,
  } = useChatStore();
  const [healthStatus, setHealthStatus] = useState<"healthy" | "degraded" | "offline">("offline");
  const [cockpits, setCockpits] = useState<Cockpit[]>([]);
  const [cockpitDropdownOpen, setCockpitDropdownOpen] = useState(false);

  // 健康检查（静默运行，仅在底部状态栏展示）
  useEffect(() => {
    let cancelled = false;
    const checkHealth = async () => {
      try {
        const h = await getHealth();
        if (!cancelled) {
          setHealthStatus(h.status === "healthy" ? "healthy" : "degraded");
        }
      } catch {
        if (!cancelled) setHealthStatus("offline");
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // 加载座舱列表
  useEffect(() => {
    let cancelled = false;
    const loadCockpits = async () => {
      try {
        const resp = await getCockpits();
        if (!cancelled && resp.cockpits) {
          setCockpits(resp.cockpits.filter((c) => c.is_active));
        }
      } catch {
        // 后端未启动时静默失败
      }
    };
    loadCockpits();
  }, []);

  // 加载会话列表
  useEffect(() => {
    if (!cockpitId) return;
    const existing = sessionsByCockpit[cockpitId];
    if (existing && existing.length > 0) return;

    listChatSessions().then((sessions) => {
      if (sessions && sessions.length > 0) {
        setSessions(cockpitId, sessions.map(s => ({
          session_id: s.session_id,
          title: s.title,
          message_count: s.message_count,
          created_at: s.created_at,
          last_message_at: s.last_message_at,
        })));
      }
    }).catch(() => {
      // 静默失败
    });
  }, [cockpitId]);

  /** 新建对话 */
  const handleNewChat = async () => {
    try {
      const sess = await createChatSession("新对话", chatUserId || userId || "default");
      newSession(sess.session_id, sess.title);
      router.push("/chat");
    } catch {
      // 后端未启动时，在前端创建临时会话
      const tempId = `temp_${Date.now()}`;
      newSession(tempId, "新对话");
      router.push("/chat");
    }
  };

  /** 切换会话 */
  const handleSwitchSession = (sid: string) => {
    setSessionId(sid);
    router.push("/chat");
  };

  /** 删除会话 */
  const handleDeleteSession = async (e: React.MouseEvent, sid: string) => {
    e.stopPropagation();
    try {
      await deleteChatSession(sid);
    } catch {
      // 静默失败
    }
    removeSession(sid);
    // 通知 Dashboard 等页面即时刷新指标数据
    window.dispatchEvent(new CustomEvent("session-deleted", { detail: { sessionId: sid } }));
  };

  const statusConfig = {
    healthy: { color: "bg-emerald-400", text: "系统运行中" },
    degraded: { color: "bg-amber-400", text: "系统降级" },
    offline: { color: "bg-red-400", text: "系统离线" },
  };
  const current = statusConfig[healthStatus];

  // 是否显示管理功能区域
  const showAdminSection =
    canViewDataPlatform(role) || canViewMiddleware(role) || canAccessSettings(role);

  // 当前选中的座舱
  const currentCockpit = cockpits.find((c) => c.cockpit_id === cockpitId);

  // 判断菜单项是否激活
  const isItemActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  // 当前座舱的会话列表
  const currentSessions = sessionsByCockpit[cockpitId] || [];
  // 是否在聊天页面
  const isChatPage = isItemActive("/chat");

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-border bg-card/50 backdrop-blur-xl">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-400 to-indigo-500">
          <Activity className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-sm font-bold gradient-text">NexusCockpit</h1>
          <p className="text-xs text-muted-foreground">智能座舱平台</p>
        </div>
      </div>

      {/* 座舱选择器 */}
      <div className="border-b border-border p-3">
        <div className="relative">
          <button
            onClick={() => setCockpitDropdownOpen(!cockpitDropdownOpen)}
            className="flex w-full items-center justify-between rounded-lg bg-accent/40 px-3 py-2 text-sm transition-colors hover:bg-accent/60"
          >
            <div className="flex items-center gap-2">
              <div
                className="h-3 w-3 rounded-full"
                style={{ backgroundColor: currentCockpit?.theme_color || "#4fc3f7" }}
              />
              <span className="font-medium">{currentCockpit?.name || cockpitId}</span>
            </div>
            <ChevronDown
              className={cn(
                "h-4 w-4 text-muted-foreground transition-transform",
                cockpitDropdownOpen && "rotate-180"
              )}
            />
          </button>

          {cockpitDropdownOpen && (
            <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-60 overflow-auto rounded-lg border border-border bg-popover p-1 shadow-xl">
              {cockpits.length > 0 ? (
                cockpits.map((c) => (
                  <button
                    key={c.cockpit_id}
                    onClick={() => {
                      switchCockpit(c.cockpit_id);
                      setCockpitIdInChat(c.cockpit_id);
                      setCockpitDropdownOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent",
                      c.cockpit_id === cockpitId && "bg-primary/10 text-primary"
                    )}
                  >
                    <div
                      className="h-3 w-3 rounded-full"
                      style={{ backgroundColor: c.theme_color }}
                    />
                    <span>{c.name}</span>
                  </button>
                ))
              ) : (
                <div className="px-3 py-2 text-xs text-muted-foreground">加载中...</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 导航区域 */}
      <nav className="flex flex-col gap-1 p-4 overflow-y-auto" style={{ maxHeight: "calc(100vh - 16rem)" }}>
        {/* 用户功能 */}
        <div className="mb-1 px-3 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
          座舱功能
        </div>
        {userNavItems.map((item) => {
          const Icon = item.icon;
          const active = isItemActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                active
                  ? "bg-primary/10 text-primary glow-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}

        {/* 聊天会话列表 — 仅在语音助手页面时显示 */}
        {isChatPage && (
          <div className="mt-2 space-y-1">
            {/* 新建对话按钮 */}
            <button
              onClick={handleNewChat}
              className="flex w-full items-center gap-2 rounded-lg border border-dashed border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary"
            >
              <Plus className="h-4 w-4" />
              新建对话
            </button>

            {/* 会话列表 */}
            {currentSessions.length > 0 && (
              <div className="space-y-0.5">
                {currentSessions.map((sess) => (
                  <div
                    key={sess.session_id}
                    onClick={() => handleSwitchSession(sess.session_id)}
                    className={cn(
                      "group flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                      sess.session_id === sessionId
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-accent"
                    )}
                  >
                    <MessageCircle className="h-3.5 w-3.5 shrink-0" />
                    <span className="flex-1 truncate text-xs">
                      {sess.title || "新对话"}
                    </span>
                    <button
                      onClick={(e) => handleDeleteSession(e, sess.session_id)}
                      className="opacity-0 transition-opacity group-hover:opacity-100"
                      title="删除对话"
                    >
                      <Trash2 className="h-3 w-3 text-muted-foreground hover:text-red-400" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 管理功能 — 仅管理员可见 */}
        {showAdminSection && (
          <>
            <div className="mb-1 mt-4 px-3 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
              管理功能
            </div>
            {adminNavItems.map((item) => {
              const Icon = item.icon;
              const active = isItemActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                    active
                      ? "bg-primary/10 text-primary glow-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </>
        )}
      </nav>

      {/* 用户信息 */}
      <div className="absolute bottom-16 left-0 right-0 px-4">
        <div className="flex items-center gap-2 rounded-lg bg-accent/30 px-3 py-2">
          <User className="h-3 w-3 text-sky-400" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium truncate">{userId || "未登录"}</p>
          </div>
          {isAuthenticated && (
            <button
              onClick={async () => {
                await apiLogout();
                authLogout();
              }}
              className="rounded-md p-1 text-muted-foreground hover:bg-red-500/10 hover:text-red-400"
              title="退出登录"
            >
              <LogOut className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      {/* 系统状态 */}
      <div className="absolute bottom-0 left-0 right-0 border-t border-border p-4">
        <div className="flex items-center gap-2 rounded-lg bg-accent/50 px-3 py-2">
          <div className={`h-2 w-2 rounded-full ${current.color} animate-pulse`} />
          <span className="text-xs text-muted-foreground">{current.text}</span>
        </div>
      </div>
    </aside>
  );
}
