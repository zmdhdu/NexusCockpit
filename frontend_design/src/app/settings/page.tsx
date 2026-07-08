"use client";

import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Key, Server, Database, Cpu, BookOpen, Upload, RefreshCw } from "lucide-react";
import { getHealth, saveConfig, getKBStats, uploadKBDocument, reindexKB } from "@/lib/api";
import { toast } from "sonner";
import type { HealthData } from "@/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [saving, setSaving] = useState(false);
  const [kbStats, setKbStats] = useState<{ connected: boolean; total_docs?: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    const fetchKBStats = async () => {
      try {
        const stats = await getKBStats();
        if (!cancelled) setKbStats(stats);
      } catch {
        if (!cancelled) setKbStats({ connected: false });
      }
    };
    checkHealth();
    fetchKBStats();
    return () => { cancelled = true; };
  }, []);

  const isConnected = health?.status === "healthy";

  // v2.0: 对接后端真实保存
  const handleSave = async () => {
    setSaving(true);
    try {
      await saveConfig({
        ark_api_key: (document.getElementById("ark-key") as HTMLInputElement)?.value || "",
        tavily_api_key: (document.getElementById("tavily-key") as HTMLInputElement)?.value || "",
        api_url: (document.getElementById("api-url") as HTMLInputElement)?.value || "",
      });
      toast.success("配置已保存", { description: "API 密钥与连接配置已更新到后端。" });
    } catch {
      toast.error("保存失败", { description: "后端接口不可用，请检查连接。" });
    } finally {
      setSaving(false);
    }
  };

  // v2.0: 知识库文档上传
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const result = await uploadKBDocument(file, "manual");
      toast.success("文档已上传", { description: `${result.chunks} 个分块已索引。` });
      // 刷新统计
      const stats = await getKBStats();
      setKbStats(stats);
    } catch {
      toast.error("上传失败", { description: "请检查文件格式和后端连接。" });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // v2.0: 重建索引
  const handleReindex = async () => {
    try {
      await reindexKB();
      toast.success("索引重建已触发", { description: "后台正在处理..." });
    } catch {
      toast.error("重建失败", { description: "后端接口不可用。" });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">设置</h1>
        <p className="text-sm text-muted-foreground">
          v2.0 系统配置与 API 密钥管理
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
              <Input id="ark-key" type="password" placeholder="sk-..." defaultValue="" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Tavily API Key</label>
              <Input id="tavily-key" type="password" placeholder="tvly-..." defaultValue="" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Langfuse Public Key</label>
              <Input type="password" placeholder="pk-..." defaultValue="" />
            </div>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? "保存中..." : "保存配置"}
            </Button>
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
              <Input id="api-url" placeholder="http://localhost:8000" defaultValue="http://localhost:8000" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">WebSocket 地址</label>
              <Input placeholder="ws://localhost:8000/ws/chat" defaultValue="ws://localhost:8000/ws/chat" />
            </div>
            <div
              className={`flex items-center gap-2 rounded-lg px-3 py-2 ${
                isConnected ? "bg-emerald-500/10" : "bg-red-500/10"
              }`}
            >
              <div
                className={`h-2 w-2 rounded-full animate-pulse ${
                  isConnected ? "bg-emerald-400" : "bg-red-400"
                }`}
              />
              <span className={`text-sm ${isConnected ? "text-emerald-400" : "text-red-400"}`}>
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
              <span className="font-medium">Qwen-Plus</span>
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
              <span className="text-muted-foreground">Rerank 模型</span>
              <span className="font-medium text-emerald-400">bge-reranker-v2-m3</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">声纹模型</span>
              <span className="font-medium">CAM++</span>
            </div>
          </CardContent>
        </Card>

        {/* v2.0: Knowledge Base Management */}
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-primary" />
              知识库管理
              {kbStats?.connected && (
                <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-400">
                  Cherry KB
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-lg bg-accent/30 p-3">
                <p className="text-xs text-muted-foreground">连接状态</p>
                <p className="text-lg font-bold">
                  {kbStats?.connected ? (
                    <span className="text-emerald-400">已连接</span>
                  ) : (
                    <span className="text-muted-foreground">未连接</span>
                  )}
                </p>
              </div>
              <div className="rounded-lg bg-accent/30 p-3">
                <p className="text-xs text-muted-foreground">文档总数</p>
                <p className="text-lg font-bold text-indigo-400">
                  {kbStats?.total_docs ?? "—"}
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">上传文档</label>
              <div className="flex gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,.md"
                  onChange={handleUpload}
                  className="hidden"
                />
                <Button
                  variant="outline"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading || !kbStats?.connected}
                  className="flex-1"
                >
                  <Upload className="h-4 w-4 mr-2" />
                  {uploading ? "上传中..." : "选择文件"}
                </Button>
                <Button
                  variant="outline"
                  onClick={handleReindex}
                  disabled={!kbStats?.connected}
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  重建索引
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                支持 .txt / .md 文件，自动分块向量化入库
              </p>
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
            {["Milvus", "Neo4j", "Redis", "RabbitMQ", "MySQL", "OSS"].map(
              (db) => {
                const dbKey = db.toLowerCase();
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
