/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Database,
  HardDrive,
  MemoryStick,
  Server,
  Activity,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Volume2,
  Mic,
} from "lucide-react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAllMiddlewareStatus } from "@/lib/api";
import { toast } from "sonner";
import type { MiddlewareStatus } from "@/types";

// 中间件图标映射
const middlewareIcons: Record<string, typeof Database> = {
  redis: Database,
  milvus: HardDrive,
  neo4j: Activity,
  rabbitmq: Server,
  mysql: Database,
  python_ai: Server,
  llm: Server,
  tts: Volume2,
  asr: Mic,
  app: Activity,
  oss: HardDrive,
};

// 中间件中文名映射
const middlewareNames: Record<string, string> = {
  redis: "Redis",
  milvus: "Milvus",
  neo4j: "Neo4j",
  rabbitmq: "RabbitMQ",
  mysql: "MySQL",
  python_ai: "Python AI 服务",
  llm: "LLM 大语言模型",
  tts: "TTS 语音合成",
  asr: "ASR 语音识别",
  app: "应用配置",
  oss: "OSS 对象存储",
};

// 健康状态集合 — 后端可能返回的 "正常" 状态值
const HEALTHY_STATUSES = new Set([
  "connected",   // Redis/Milvus/Neo4j/RabbitMQ/MySQL 连接成功
  "online",      // 在线
  "available",   // LLM/TTS/ASR/OSS 已配置且可用
  "running",     // 应用运行中
  "configured",  // OSS 已配置（endpoint 存在但未完整启用）
]);

// 状态文案映射 — 中文友好显示
const STATUS_LABELS: Record<string, string> = {
  connected: "已连接",
  online: "在线",
  available: "可用",
  running: "运行中",
  configured: "已配置",
  disconnected: "未连接",
  not_configured: "未配置",
  not_installed: "未安装",
  model_not_found: "模型缺失",
};
const middlewareColors: Record<string, string> = {
  redis: "text-red-400",
  milvus: "text-sky-400",
  neo4j: "text-emerald-400",
  rabbitmq: "text-orange-400",
  mysql: "text-blue-400",
  python_ai: "text-violet-400",
  llm: "text-indigo-400",
  tts: "text-pink-400",
  asr: "text-cyan-400",
  app: "text-emerald-400",
  oss: "text-amber-400",
};

export default function MiddlewarePage() {
  const [statuses, setStatuses] = useState<Record<string, MiddlewareStatus>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (showToast = false) => {
    if (showToast) setRefreshing(true);
    try {
      const data = await getAllMiddlewareStatus();
      setStatuses(data);
      if (showToast) toast.success("中间件状态已刷新");
    } catch {
      toast.error("中间件状态获取失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(), 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const middlewareEntries = Object.entries(statuses);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">系统监控</h1>
          <p className="text-sm text-muted-foreground">
            各座舱基础设施运行状态一览
          </p>
        </div>
        <button
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="flex items-center gap-2 rounded-lg bg-primary/10 px-4 py-2 text-sm font-medium text-primary transition-all hover:bg-primary/20 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          刷新
        </button>
      </div>

      {/* 概览卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-5 lg:grid-cols-10 gap-3">
        {middlewareEntries.map(([key, status], index) => {
          const Icon = middlewareIcons[key] || Database;
          const color = middlewareColors[key] || "text-muted-foreground";
          const isConnected = HEALTHY_STATUSES.has(status.status);
          const name = middlewareNames[key] || status.name || key;

          return (
            <motion.div
              key={key}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
            >
              <Card className="glass">
                <CardContent className="p-4">
                  <div className="flex flex-col items-center gap-2 text-center">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/50">
                      <Icon className={`h-5 w-5 ${color}`} />
                    </div>
                    <p className="text-sm font-bold">{name}</p>
                    <div className="flex items-center gap-1">
                      {isConnected ? (
                        <>
                          <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                          <span className="text-xs text-emerald-400">{STATUS_LABELS[status.status] || "正常"}</span>
                        </>
                      ) : (
                        <>
                          <XCircle className="h-3 w-3 text-red-400" />
                          <span className="text-xs text-red-400">{STATUS_LABELS[status.status] || status.status}</span>
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
        {middlewareEntries.length === 0 && loading && (
          <div className="col-span-5 py-8 text-center text-muted-foreground">加载中...</div>
        )}
      </div>

      {/* 详细状态卡片 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {middlewareEntries.map(([key, status], index) => {
          const Icon = middlewareIcons[key] || Database;
          const color = middlewareColors[key] || "text-muted-foreground";
          const isConnected = HEALTHY_STATUSES.has(status.status);
          const name = middlewareNames[key] || status.name || key;

          return (
            <motion.div
              key={`detail-${key}`}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.1 + index * 0.1, duration: 0.4 }}
            >
              <Card className="glass">
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Icon className={`h-5 w-5 ${color}`} />
                      {name}
                    </div>
                    <span
                      className={`rounded px-2 py-1 text-xs ${
                        isConnected
                          ? "bg-emerald-500/10 text-emerald-400"
                          : "bg-red-500/10 text-red-400"
                      }`}
                    >
                      {isConnected ? (STATUS_LABELS[status.status] || "运行中") : (STATUS_LABELS[status.status] || status.status)}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {isConnected ? (
                    <div className="space-y-2">
                      {/* 动态渲染状态字段 */}
                      {Object.entries(status)
                        .filter(([k]) => !["name", "status", "error"].includes(k))
                        .map(([field, value]) => (
                          <div
                            key={field}
                            className="flex items-center justify-between rounded-lg bg-accent/30 px-3 py-2"
                          >
                            <span className="text-xs text-muted-foreground">
                              {field.replace(/_/g, " ")}
                            </span>
                            <span className="text-sm font-medium">
                              {typeof value === "object"
                                ? JSON.stringify(value)
                                : String(value)}
                            </span>
                          </div>
                        ))}
                    </div>
                  ) : (
                    <div className="rounded-lg bg-red-500/5 p-3">
                      <p className="text-sm text-red-400">
                        {status.error || "连接失败"}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>

      {/* 隔离信息说明 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5, duration: 0.4 }}
      >
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MemoryStick className="h-5 w-5 text-primary" />
              座舱数据隔离
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-lg bg-accent/30 p-4">
                <p className="text-sm font-bold text-red-400">缓存隔离</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  每个座舱独立缓存分区，互不干扰
                </p>
              </div>
              <div className="rounded-lg bg-accent/30 p-4">
                <p className="text-sm font-bold text-sky-400">知识库隔离</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  每个座舱独立向量索引，数据物理隔离
                </p>
              </div>
              <div className="rounded-lg bg-accent/30 p-4">
                <p className="text-sm font-bold text-blue-400">业务数据隔离</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  所有业务表按座舱 ID 过滤，确保数据安全
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
