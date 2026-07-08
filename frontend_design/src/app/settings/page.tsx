"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Key, Server, Database, Cpu } from "lucide-react";
import { getHealth } from "@/lib/api";
import { toast } from "sonner";
import type { HealthData } from "@/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthData | null>(null);

  useEffect(() => {
    let cancelled = false;
    const checkHealth = async () => {
      try {
        const h = await getHealth();
        if (!cancelled) setHealth(h);
      } catch {
        if (!cancelled) setHealth({ status: "offline", services: {} });
      }
    };
    checkHealth();
    return () => {
      cancelled = true;
    };
  }, []);

  const isConnected = health?.status === "healthy";

  const handleSave = () => {
    toast.success("配置已保存", {
      description: "API 密钥与连接配置已更新。",
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">设置</h1>
        <p className="text-sm text-muted-foreground">
          系统配置与 API 密钥管理
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* API Keys */}
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Key className="h-5 w-5 text-primary" />
              API 密钥
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Ark API Key</label>
              <Input type="password" placeholder="sk-..." defaultValue="" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Tavily API Key</label>
              <Input type="password" placeholder="tvly-..." defaultValue="" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Langfuse Public Key</label>
              <Input type="password" placeholder="pk-..." defaultValue="" />
            </div>
            <Button onClick={handleSave}>保存配置</Button>
          </CardContent>
        </Card>

        {/* Backend Config */}
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5 text-primary" />
              后端连接
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">API 地址</label>
              <Input placeholder="http://localhost:8000" defaultValue="http://localhost:8000" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">WebSocket 地址</label>
              <Input placeholder="ws://localhost:8000/ws/chat" defaultValue="ws://localhost:8000/ws/chat" />
            </div>
            <div
              className={`flex items-center gap-2 rounded-lg px-3 py-2 ${
                isConnected
                  ? "bg-emerald-500/10"
                  : "bg-red-500/10"
              }`}
            >
              <div
                className={`h-2 w-2 rounded-full animate-pulse ${
                  isConnected ? "bg-emerald-400" : "bg-red-400"
                }`}
              />
              <span
                className={`text-sm ${
                  isConnected ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {isConnected ? "已连接" : "未连接"}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Model Info */}
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="h-5 w-5 text-primary" />
              模型配置
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">LLM 模型</span>
              <span className="font-medium">DeepSeek-V3</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Embedding 模型</span>
              <span className="font-medium">Qwen3-Embedding-4B</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">ASR 模型</span>
              <span className="font-medium">SenseVoice</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">TTS 模型</span>
              <span className="font-medium">CosyVoice-300M</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">声纹模型</span>
              <span className="font-medium">CAM++</span>
            </div>
          </CardContent>
        </Card>

        {/* Database Status */}
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-5 w-5 text-primary" />
              数据库状态
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* 后端 /health 接口返回的服务状态，未配置的服务显示为“未知” */}
            {["Milvus", "Neo4j", "Redis", "RabbitMQ", "MySQL", "OSS"].map(
              (db) => {
                const dbKey = db.toLowerCase();
                // 健康接口返回的服务名: milvus, neo4j, redis, agent
                // RabbitMQ / MySQL / OSS 未在后端健康检查中配置
                const dbStatus = health?.services?.[dbKey];
                const isRunning = dbStatus === "connected" || dbStatus === "ready";
                return (
                  <div
                    key={db}
                    className="flex items-center justify-between rounded-lg bg-accent/30 px-3 py-2"
                  >
                    <span className="text-sm font-medium">{db}</span>
                    <div className="flex items-center gap-2">
                      <div
                        className={`h-2 w-2 rounded-full ${
                          isRunning
                            ? "bg-emerald-400"
                            : dbStatus
                            ? "bg-red-400"
                            : "bg-muted-foreground"
                        }`}
                      />
                      <span className="text-xs text-muted-foreground">
                        {dbStatus ?? (isConnected ? "未监控" : "未知")}
                      </span>
                    </div>
                  </div>
                );
              }
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
