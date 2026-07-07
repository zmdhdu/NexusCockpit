"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  MessageSquare,
  Car,
  Zap,
  Clock,
  TrendingUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getHealth, getCacheStats } from "@/lib/api";

interface HealthData {
  status: string;
  services: Record<string, string>;
}

interface CacheStats {
  hits: number;
  misses: number;
  hit_rate: number;
  size: number;
}

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [cache, setCache] = useState<CacheStats | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const h = await getHealth();
        setHealth(h);
      } catch {
        setHealth({ status: "offline", services: {} });
      }
      try {
        const c = await getCacheStats();
        setCache(c);
      } catch {
        setCache({ hits: 0, misses: 0, hit_rate: 0, size: 0 });
      }
    };
    fetchData();
  }, []);

  const stats = [
    {
      label: "对话总数",
      value: "1,284",
      icon: MessageSquare,
      change: "+12.5%",
      color: "text-sky-400",
    },
    {
      label: "车控指令",
      value: "456",
      icon: Car,
      change: "+8.2%",
      color: "text-indigo-400",
    },
    {
      label: "缓存命中",
      value: cache ? `${cache.hit_rate}%` : "—",
      icon: Zap,
      change: cache ? `${cache.hits} hits` : "",
      color: "text-emerald-400",
    },
    {
      label: "平均响应",
      value: "320ms",
      icon: Clock,
      change: "-15ms",
      color: "text-amber-400",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">仪表盘</h1>
          <p className="text-sm text-muted-foreground">
            NexusCockpit 系统总览
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-emerald-500/10 px-3 py-1.5">
          <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-sm text-emerald-400">
            {health?.status === "healthy" ? "系统正常" : "连接中..."}
          </span>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label} className="glass hover:glow-primary transition-all">
              <CardContent className="p-5">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <p className="text-sm text-muted-foreground">{stat.label}</p>
                    <p className="text-2xl font-bold">{stat.value}</p>
                    <p className="text-xs text-emerald-400 flex items-center gap-1">
                      <TrendingUp className="h-3 w-3" />
                      {stat.change}
                    </p>
                  </div>
                  <div className={`flex h-12 w-12 items-center justify-center rounded-xl bg-accent/50`}>
                    <Icon className={`h-6 w-6 ${stat.color}`} />
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Service Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              服务状态
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {health?.services ? (
                Object.entries(health.services).map(([name, status]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between rounded-lg bg-accent/30 px-3 py-2"
                  >
                    <span className="text-sm font-medium">{name}</span>
                    <div className="flex items-center gap-2">
                      <div
                        className={`h-2 w-2 rounded-full ${
                          status === "connected" || status === "ready"
                            ? "bg-emerald-400"
                            : "bg-red-400"
                        }`}
                      />
                      <span className="text-xs text-muted-foreground">{status}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-muted-foreground">加载中...</div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-primary" />
              缓存统计
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-lg bg-accent/30 p-3">
                <p className="text-xs text-muted-foreground">命中次数</p>
                <p className="text-xl font-bold text-emerald-400">
                  {cache?.hits ?? "—"}
                </p>
              </div>
              <div className="rounded-lg bg-accent/30 p-3">
                <p className="text-xs text-muted-foreground">未命中</p>
                <p className="text-xl font-bold text-amber-400">
                  {cache?.misses ?? "—"}
                </p>
              </div>
              <div className="rounded-lg bg-accent/30 p-3">
                <p className="text-xs text-muted-foreground">命中率</p>
                <p className="text-xl font-bold text-sky-400">
                  {cache ? `${cache.hit_rate}%` : "—"}
                </p>
              </div>
              <div className="rounded-lg bg-accent/30 p-3">
                <p className="text-xs text-muted-foreground">缓存大小</p>
                <p className="text-xl font-bold text-indigo-400">
                  {cache?.size ?? "—"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
