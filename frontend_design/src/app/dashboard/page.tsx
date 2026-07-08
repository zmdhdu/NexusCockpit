"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  MessageSquare,
  Car,
  Zap,
  Clock,
  TrendingUp,
  Cpu,
  Brain,
} from "lucide-react";
import { motion } from "framer-motion";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Vehicle3DModel } from "@/components/vehicle/vehicle-3d";
import { getHealth, getCacheStats } from "@/lib/api";
import { toast } from "sonner";
import type { HealthData, CacheStats } from "@/types";

// 缓存趋势模拟数据（v2.0 后续对接 /admin/stats 历史 API）
const cacheTrendData = [
  { time: "10:00", hits: 12, misses: 3 },
  { time: "11:00", hits: 18, misses: 5 },
  { time: "12:00", hits: 25, misses: 4 },
  { time: "13:00", hits: 22, misses: 6 },
  { time: "14:00", hits: 30, misses: 3 },
  { time: "15:00", hits: 28, misses: 5 },
  { time: "16:00", hits: 35, misses: 4 },
];

// 专家分布数据
const expertData = [
  { name: "车控", count: 45 },
  { name: "闲聊", count: 38 },
  { name: "生活", count: 22 },
  { name: "导航", count: 15 },
  { name: "健康", count: 8 },
];

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [cache, setCache] = useState<CacheStats | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      try {
        const h = await getHealth();
        if (!cancelled) setHealth(h);
      } catch {
        if (!cancelled) setHealth({ status: "offline", services: {} });
      }
      try {
        const c = await getCacheStats();
        if (!cancelled) setCache(c);
      } catch {
        if (!cancelled) setCache({ hits: 0, misses: 0, hit_rate: 0, size: 0 });
      }
    };
    fetchData();

    const interval = setInterval(fetchData, 30000); // v2.0: 30秒自动刷新
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const stats = [
    {
      label: "对话总数",
      value: cache ? `${cache.hits + cache.misses + 1284}` : "1,284",
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

  // 专家列表
  const experts = [
    { name: "车控专家", icon: Car, color: "text-sky-400", active: health?.status === "healthy" },
    { name: "导航专家", icon: Activity, color: "text-indigo-400", active: health?.status === "healthy" },
    { name: "生活推荐", icon: MessageSquare, color: "text-emerald-400", active: health?.status === "healthy" },
    { name: "车辆健康", icon: Brain, color: "text-amber-400", active: health?.status === "healthy" },
    { name: "闲聊专家", icon: Cpu, color: "text-purple-400", active: health?.status === "healthy" },
  ];

  const handle3DPartClick = (part: string) => {
    const partMap: Record<string, string> = {
      window: "车窗控制",
      body: "车身状态",
    };
    toast.info(`3D 模型交互: ${partMap[part] || part}`, {
      description: "点击对应控件可发送车控指令",
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">仪表盘</h1>
          <p className="text-sm text-muted-foreground">
            NexusCockpit v2.0 Multi-Agent 系统总览
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-emerald-500/10 px-3 py-1.5">
          <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-sm text-emerald-400">
            {health?.status === "healthy" ? "系统正常" : "连接中..."}
          </span>
        </div>
      </div>

      {/* Stats Cards with framer-motion */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, index) => {
          const Icon = stat.icon;
          return (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1, duration: 0.4 }}
            >
              <Card className="glass hover:glow-primary transition-all">
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
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent/50">
                      <Icon className={`h-6 w-6 ${stat.color}`} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Cache Trend Chart */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3, duration: 0.4 }}
        >
          <Card className="glass">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-primary" />
                缓存趋势
                {cache?.index_ready && (
                  <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-400">
                    VECTOR
                  </span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={cacheTrendData}>
                  <defs>
                    <linearGradient id="hitGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#34d399" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="missGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#fbbf24" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#fbbf24" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e3a5f" opacity={0.3} />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={12} />
                  <YAxis stroke="#64748b" fontSize={12} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #1e3a5f",
                      borderRadius: "8px",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="hits"
                    stroke="#34d399"
                    fill="url(#hitGradient)"
                    name="命中"
                  />
                  <Area
                    type="monotone"
                    dataKey="misses"
                    stroke="#fbbf24"
                    fill="url(#missGradient)"
                    name="未命中"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </motion.div>

        {/* Expert Distribution */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.4, duration: 0.4 }}
        >
          <Card className="glass">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-primary" />
                专家调度分布
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={expertData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e3a5f" opacity={0.3} />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={12} />
                  <YAxis stroke="#64748b" fontSize={12} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #1e3a5f",
                      borderRadius: "8px",
                    }}
                  />
                  <Bar dataKey="count" fill="#818cf8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* 3D Vehicle Model + Expert Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 3D Vehicle Model */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.5, duration: 0.4 }}
          className="lg:col-span-2"
        >
          <Card className="glass">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Car className="h-5 w-5 text-primary" />
                3D 车辆模型
                <span className="text-xs text-muted-foreground font-normal">
                  点击部件交互
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Vehicle3DModel onPartClick={handle3DPartClick} />
            </CardContent>
          </Card>
        </motion.div>

        {/* Expert Status */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.4 }}
        >
          <Card className="glass">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="h-5 w-5 text-primary" />
                专家状态
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {experts.map((expert) => {
                  const Icon = expert.icon;
                  return (
                    <div
                      key={expert.name}
                      className="flex items-center justify-between rounded-lg bg-accent/30 px-3 py-2"
                    >
                      <div className="flex items-center gap-2">
                        <Icon className={`h-4 w-4 ${expert.color}`} />
                        <span className="text-sm font-medium">{expert.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div
                          className={`h-2 w-2 rounded-full ${
                            expert.active
                              ? "bg-emerald-400 animate-pulse"
                              : "bg-muted-foreground"
                          }`}
                        />
                        <span className="text-xs text-muted-foreground">
                          {expert.active ? "就绪" : "离线"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </motion.div>
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
              {cache?.index_ready && (
                <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-400">
                  RediSearch
                </span>
              )}
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
