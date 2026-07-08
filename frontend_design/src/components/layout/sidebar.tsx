/**
 * 侧边栏组件 — 固定在页面左侧的导航栏
 *
 * 包含: Logo、导航菜单、系统状态指示灯
 * 使用 usePathname() 判断当前活跃页面并高亮显示
 */
"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, MessageSquare, Car, Settings, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { getHealth } from "@/lib/api";

// 导航菜单项配置
const navItems = [
  { href: "/dashboard", label: "仪表盘", icon: LayoutDashboard },
  { href: "/chat", label: "语音助手", icon: MessageSquare },
  { href: "/vehicle", label: "车控面板", icon: Car },
  { href: "/settings", label: "设置", icon: Settings },
];

/** 侧边栏组件 */
export function Sidebar() {
  // 获取当前路由路径，用于判断哪个导航项是活跃的
  const pathname = usePathname();
  const [healthStatus, setHealthStatus] = useState<"healthy" | "degraded" | "offline">("offline");

  // 定时轮询后端健康状态 (每 30 秒)
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

  const statusConfig = {
    healthy: { color: "bg-emerald-400", text: "系统运行中" },
    degraded: { color: "bg-amber-400", text: "系统降级" },
    offline: { color: "bg-red-400", text: "系统离线" },
  };
  const current = statusConfig[healthStatus];

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-border bg-card/50 backdrop-blur-xl">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-400 to-indigo-500">
          <Activity className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-sm font-bold gradient-text">NexusCockpit</h1>
          <p className="text-xs text-muted-foreground">Vehicle Voice Agent</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1 p-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
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
      </nav>

      {/* Status — 动态显示后端健康状态 */}
      <div className="absolute bottom-0 left-0 right-0 border-t border-border p-4">
        <div className="flex items-center gap-2 rounded-lg bg-accent/50 px-3 py-2">
          <div className={`h-2 w-2 rounded-full ${current.color} animate-pulse`} />
          <span className="text-xs text-muted-foreground">{current.text}</span>
        </div>
      </div>
    </aside>
  );
}
