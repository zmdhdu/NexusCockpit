/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  MessageSquare,
  Car,
  Zap,
  Clock,
  TrendingUp,
  Brain,
  Shield,
  AlertTriangle,
  Gauge,
  Server,
  CheckCircle2,
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
import {
  getHealth,
  getCacheStats,
  getDataPlatformOverview,
  getCockpitComparison,
  getCacheTrend,
  getAlerts,
  getAgentActivity,
} from "@/lib/api";
import type {
  HealthData,
  CacheStats,
  DataPlatformOverview,
  CockpitComparison,
  AlertRecord,
  AgentActivity,
} from "@/types";

/**
 * 运营总览页 — 管理员视角的系统全景看板
 *
 * 展示内容:
 *   1. 关键指标卡片（对话量、车控量、缓存命中率、平均延迟）
 *   2. 各座舱健康状态对比
 *   3. AI 引擎状态（Supervisor + 5 Expert Agents）
 *   4. 缓存趋势图 & 服务调度分布
 *   5. 24h 告警记录
 *   6. 服务状态一览
 */
export default function DashboardPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [cache, setCache] = useState<CacheStats | null>(null);
  const [overview, setOverview] = useState<DataPlatformOverview | null>(null);
  const [comparison, setComparison] = useState<CockpitComparison[]>([]);
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [activities, setActivities] = useState<AgentActivity[]>([]);
  const [cacheTrendData, setCacheTrendData] = useState<{ time: string; hits: number; misses: number }[]>(
    Array.from({ length: 13 }, (_, i) => ({ time: `${String(i * 2).padStart(2, "0")}:00`, hits: 0, misses: 0 }))
  );

  // 数据刷新函数 — 可被会话删除等事件触发即时刷新
  const fetchAllData = async () => {
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
    try {
      const ov = await getDataPlatformOverview();
      setOverview(ov);
    } catch {
      // 静默处理
    }
    try {
      const cmp = await getCockpitComparison();
      setComparison(cmp);
    } catch {
      // 静默处理
    }
    try {
      const trend = await getCacheTrend();
      if (trend && trend.length > 0) setCacheTrendData(trend);
    } catch {
      // 静默处理
    }
    try {
      const alrt = await getAlerts(24);
      setAlerts(alrt);
    } catch {
      // 静默处理
    }
    try {
      const act = await getAgentActivity(24);
      setActivities(act);
    } catch {
      // 静默处理
    }
  };

  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      if (cancelled) return;
      await fetchAllData();
    };
    fetchData();

    // 监听会话删除事件，即时刷新看板数据
    const handleSessionDeleted = () => {
      fetchData();
    };
    window.addEventListener("session-deleted", handleSessionDeleted);

    const interval = setInterval(fetchData, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
      window.removeEventListener("session-deleted", handleSessionDeleted);
    };
  }, []);

  // 关键指标
  const stats = [
    {
      label: "对话总数",
      value: overview ? `${overview.total_chats}` : cache ? `${cache.hits + cache.misses + 1284}` : "—",
      icon: MessageSquare,
      change: "+12.5%",
      color: "text-sky-400",
    },
    {
      label: "车控指令",
      value: overview ? `${overview.total_vehicle_cmds}` : "—",
      icon: Car,
      change: "+8.2%",
      color: "text-indigo-400",
    },
    {
      label: "缓存命中率",
      value: overview ? `${overview.cache_hit_rate}%` : cache ? `${cache.hit_rate}%` : "—",
      icon: Zap,
      change: cache ? `${cache.hits} 命中` : "",
      color: "text-emerald-400",
    },
    {
      label: "平均响应",
      value: overview ? `${overview.avg_latency_ms}ms` : "—",
      icon: Clock,
      change: "-15ms",
      color: "text-amber-400",
    },
  ];

  const agentReady = health?.services?.agent === "ready";

  // 引擎状态 — Supervisor 为调度核心，Expert Agents 为并行执行单元
  const engines = [
    {
      name: "Supervisor 引擎",
      desc: "记忆召回 + 意图路由 + 专家调度",
      icon: Shield,
      color: "text-sky-400",
      active: agentReady,
      statusLabel: agentReady ? "运行中" : "待启动",
    },
    {
      name: "Expert 引擎",
      desc: "5 专家并行执行（车控/导航/生活/健康/闲聊）",
      icon: Brain,
      color: "text-amber-400",
      active: agentReady,
      statusLabel: agentReady ? "运行中" : "待启动",
    },
  ];

  // 引擎详情 — Supervisor 节点 + Expert 专家列表
  const supervisorNodes = [
    { name: "记忆召回", desc: "GraphRAG 三路融合检索" },
    { name: "意图路由", desc: "启发式 + LLM 双策略" },
    { name: "专家分派", desc: "asyncio.gather 并行" },
    { name: "反思校验", desc: "CoT 自我批评" },
    { name: "结果审查", desc: "记忆存储 + 指标" },
  ];
  const expertAgents = [
    { name: "车控专家", desc: "空调/车窗/灯光" },
    { name: "导航专家", desc: "路线/POI 搜索" },
    { name: "生活专家", desc: "天气/美食/搜索" },
    { name: "健康专家", desc: "习惯/提醒" },
    { name: "闲聊专家", desc: "日常对话" },
  ];

  // 缓存趋势数据 — 从后端 /dataplatform/cache-trend 获取真实数据（2小时间隔）
  // cacheTrendData state 已在组件顶部初始化，数据由 fetchAllData 填充

  // 座舱状态列表
  const cockpitStatuses = comparison.length > 0 ? comparison : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">运营总览</h1>
          <p className="text-sm text-muted-foreground">
            全部座舱运营数据与系统健康状态
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-emerald-500/10 px-3 py-1.5">
          <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-sm text-emerald-400">
            {health?.status === "healthy" ? "系统正常" : "连接中..."}
          </span>
        </div>
      </div>

      {/* 座舱状态条 */}
      {cockpitStatuses.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 overflow-x-auto pb-2"
        >
          {cockpitStatuses.map((c) => (
            <div
              key={c.cockpit_id}
              className="flex items-center gap-2 rounded-lg bg-accent/30 px-4 py-2 whitespace-nowrap"
            >
              <Gauge className="h-4 w-4 text-sky-400" />
              <span className="text-sm font-medium">{c.name}</span>
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] ${
                  c.health_score >= 80
                    ? "bg-emerald-500/10 text-emerald-400"
                    : c.health_score >= 60
                    ? "bg-amber-500/10 text-amber-400"
                    : "bg-red-500/10 text-red-400"
                }`}
              >
                {c.health_score}
              </span>
            </div>
          ))}
        </motion.div>
      )}

      {/* 关键指标卡片 */}
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

      {/* 引擎状态（左 1/2） + 缓存趋势（右上 1/2） + 座舱对比（右下 1/2） */}
      {/* 高度调小一点；grid-rows-2 让右侧缓存趋势与座舱对比均分高度，避免图表撑高第一行压挤座舱对比 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 lg:grid-rows-2 gap-4 lg:h-[760px]">
        {/* 引擎状态 — 占左侧，跨 2 行 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.4 }}
          className="lg:row-span-2 min-h-0"
        >
          <Card className="glass h-full flex flex-col overflow-hidden">
            <CardHeader className="flex-shrink-0">
              <CardTitle className="flex items-center gap-2">
                <Brain className="h-6 w-6 text-primary" />
                <span className="text-lg">引擎状态</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 min-h-0">
              <div className="space-y-3">
                {engines.map((engine) => {
                  const Icon = engine.icon;
                  return (
                    <div key={engine.name} className="rounded-lg bg-accent/30 p-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <Icon className={`h-5 w-5 ${engine.color}`} />
                          <div>
                            <span className="text-base font-semibold">{engine.name}</span>
                            <p className="text-sm text-muted-foreground mt-1">{engine.desc}</p>
                          </div>
                        </div>
                        <span
                          className={`rounded px-2.5 py-1 text-sm ${
                            engine.active
                              ? "bg-emerald-500/10 text-emerald-400"
                              : "bg-muted/20 text-muted-foreground"
                          }`}
                        >
                          {engine.statusLabel}
                        </span>
                      </div>
                    </div>
                  );
                })}

                {/* 引擎详情 — Supervisor 节点 + Expert 专家 */}
                <div className="pt-1 space-y-3">
                  {/* Supervisor 节点 */}
                  <div>
                    <p className="text-sm font-medium text-muted-foreground mb-2">Supervisor 节点</p>
                    <div className="space-y-1.5">
                      {supervisorNodes.map((node, idx) => (
                        <div
                          key={node.name}
                          className="flex items-center justify-between rounded-md bg-accent/20 px-4 py-2"
                        >
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-muted-foreground">L{idx + 1}</span>
                            <span className="text-sm font-medium">{node.name}</span>
                          </div>
                          <span className="text-sm text-muted-foreground">{node.desc}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Expert 专家 */}
                  <div>
                    <p className="text-sm font-medium text-muted-foreground mb-2">Expert 专家</p>
                    <div className="grid grid-cols-1 gap-1.5">
                      {expertAgents.map((agent) => (
                        <div
                          key={agent.name}
                          className="flex items-center justify-between rounded-md bg-accent/20 px-4 py-2"
                        >
                          <span className="text-sm font-medium">{agent.name}</span>
                          <span className="text-sm text-muted-foreground">{agent.desc}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* 缓存趋势（右上） */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.4, duration: 0.4 }}
          className="min-h-0"
        >
          <Card className="glass h-full flex flex-col overflow-hidden">
            <CardHeader className="flex-shrink-0">
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-primary" />
                缓存趋势
                {cache?.index_ready && (
                  <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-400">
                    索引就绪
                  </span>
                )}
              </CardTitle>
            </CardHeader>
            {/* flex-1 + min-h-0 让图表容器获得确定高度，ResponsiveContainer 才能正确自适应 */}
            <CardContent className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={cacheTrendData}
                  margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
                >
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
                  <XAxis
                    dataKey="time"
                    stroke="#64748b"
                    fontSize={12}
                    interval={0}
                    padding={{ left: 10, right: 20 }}
                  />
                  {/* width=20 让纵坐标左移对齐闪电图标下方；domain [0,50] + ticks 间隔 10 */}
                  <YAxis
                    stroke="#64748b"
                    fontSize={12}
                    width={20}
                    domain={[0, 50]}
                    ticks={[0, 10, 20, 30, 40, 50]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #1e3a5f",
                      borderRadius: "8px",
                    }}
                    // cursor 始终显示垂直辅助线，让用户在曲线任意位置都能看到数值
                    cursor={{ stroke: "#3b82f6", strokeWidth: 1, strokeDasharray: "4 4" }}
                    // isAnimationActive={false} 避免动画延迟导致 tooltip 闪烁
                    isAnimationActive={false}
                  />
                  <Area
                    type="monotone"
                    dataKey="hits"
                    stroke="#34d399"
                    fill="url(#hitGradient)"
                    name="命中"
                    // activeDot 让悬停时的高亮点更明显
                    activeDot={{ r: 5, fill: "#34d399", stroke: "#0f172a", strokeWidth: 2 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="misses"
                    stroke="#fbbf24"
                    fill="url(#missGradient)"
                    name="未命中"
                    activeDot={{ r: 5, fill: "#fbbf24", stroke: "#0f172a", strokeWidth: 2 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </motion.div>

        {/* 座舱运营对比（右下，与缓存趋势纵向堆叠） */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.5, duration: 0.4 }}
          className="min-h-0"
        >
          <Card className="glass h-full flex flex-col overflow-hidden">
            <CardHeader className="flex-shrink-0">
              <CardTitle className="flex items-center gap-2">
                <Gauge className="h-5 w-5 text-primary" />
                座舱运营对比
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-auto min-h-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="pb-3 text-left font-medium">座舱</th>
                      <th className="pb-3 text-right font-medium">对话</th>
                      <th className="pb-3 text-right font-medium">车控</th>
                      <th className="pb-3 text-right font-medium">命中率</th>
                      <th className="pb-3 text-right font-medium">延迟</th>
                      <th className="pb-3 text-right font-medium">健康分</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cockpitStatuses.length > 0 ? (
                      cockpitStatuses.map((c) => (
                        <tr key={c.cockpit_id} className="border-b border-border/50">
                          <td className="py-3 font-medium">{c.name}</td>
                          <td className="py-3 text-right text-sky-400">{c.chat_count}</td>
                          <td className="py-3 text-right text-indigo-400">{c.vehicle_cmd_count}</td>
                          <td className="py-3 text-right text-emerald-400">{c.vehicle_cmd_success_rate}%</td>
                          <td className="py-3 text-right text-amber-400">{c.avg_latency_ms}ms</td>
                          <td className="py-3 text-right">
                            <span
                              className={`rounded px-2 py-0.5 text-xs ${
                                c.health_score >= 80
                                  ? "bg-emerald-500/10 text-emerald-400"
                                  : c.health_score >= 60
                                  ? "bg-amber-500/10 text-amber-400"
                                  : "bg-red-500/10 text-red-400"
                              }`}
                            >
                              {c.health_score}
                            </span>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-muted-foreground">
                          暂无数据
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* 引擎活动时间线（左） + 24h 告警记录（右） */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 引擎活动时间线 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.4 }}
        >
          <Card className="glass h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-primary" />
                引擎活动时间线
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {activities.length > 0 ? (
                  activities.map((act) => (
                    <div
                      key={act.id}
                      className="flex items-start gap-3 rounded-lg bg-accent/30 p-3"
                    >
                      <div
                        className={`mt-1 h-2 w-2 rounded-full flex-shrink-0 ${
                          act.is_anomaly ? "bg-red-400" : "bg-emerald-400"
                        }`}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">
                            {act.cockpit_id}
                            {act.is_anomaly && (
                              <span className="ml-2 rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-400">
                                异常
                              </span>
                            )}
                          </span>
                          <span className="text-xs text-muted-foreground flex-shrink-0 ml-2">{act.check_time}</span>
                        </div>
                        {/* LLM 判断摘要 */}
                        {(act as any).llm_summary && (
                          <p className="mt-1 text-xs text-amber-400/80">
                            {(act as any).llm_summary}
                          </p>
                        )}
                        {/* 检查项摘要 */}
                        {(act as any).check_summary ? (
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            检查项: {(act as any).check_summary}
                          </p>
                        ) : act.check_items ? (
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            检查项: {typeof act.check_items === "string" ? act.check_items : JSON.stringify(act.check_items)}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                    暂无活动记录
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* 24h 告警 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7, duration: 0.4 }}
        >
          <Card className="glass h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-400" />
                24h 告警记录
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {alerts.length > 0 ? (
                  alerts.map((alert) => (
                    <div
                      key={alert.id}
                      className="rounded-lg bg-accent/30 p-3 text-sm"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{alert.cockpit_id}</span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] ${
                            alert.severity === "critical"
                              ? "bg-red-500/10 text-red-400"
                              : alert.severity === "warning"
                              ? "bg-amber-500/10 text-amber-400"
                              : "bg-sky-500/10 text-sky-400"
                          }`}
                        >
                          {alert.severity}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {alert.alert_type} — {alert.action_taken}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{alert.alert_time}</p>
                    </div>
                  ))
                ) : (
                  <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                    <div className="text-center">
                      <CheckCircle2 className="mx-auto mb-2 h-8 w-8 text-emerald-400/50" />
                      暂无告警
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
