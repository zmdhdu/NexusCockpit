/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Car,
  Users,
  Database,
  Plus,
  Trash2,
  ShieldCheck,
  Server,
  RefreshCw,
} from "lucide-react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import {
  getCockpits,
  registerCockpit,
  deleteCockpit,
  getUsers,
  registerUser,
  getMiddlewareConfig,
  updateMiddlewareConfig,
} from "@/lib/api";
import type { Cockpit, User } from "@/types";

/**
 * 管理设置页 — 仅管理员可访问
 *
 * 包含三个 Tab:
 *   1. 座舱管理 — 注册/注销/查看座舱
 *   2. 用户管理 — 添加/查看用户
 *   3. 系统配置 — 中间件参数热加载
 */
export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<"cockpits" | "users" | "config">("cockpits");
  const [cockpits, setCockpits] = useState<Cockpit[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [mwConfig, setMwConfig] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  // 座舱表单
  const [showCockpitForm, setShowCockpitForm] = useState(false);
  const [cockpitForm, setCockpitForm] = useState({
    name: "",
    user_id: "",
    vehicle_adapter: "mock",
    theme_color: "#38bdf8",
  });

  // 用户表单
  const [showUserForm, setShowUserForm] = useState(false);
  const [userForm, setUserForm] = useState({
    user_id: "",
    username: "",
    cockpit_id: "cockpit-01",
    role: "cockpit_user",
  });

  /**
   * 生成随机用户名 — 字母 + 下划线 + 数字组合，数字不开头
   * 示例: kx7m2_pq, ab_38cd, user_1a2b
   */
  const generateUsername = useCallback((): string => {
    const letters = "abcdefghijklmnopqrstuvwxyz";
    const chars = letters + "0123456789";
    const length = 6 + Math.floor(Math.random() * 4); // 6-9 位
    let result = letters[Math.floor(Math.random() * letters.length)]; // 首位必须是字母
    for (let i = 1; i < length; i++) {
      if (i === 3 && Math.random() > 0.5) {
        result += "_"; // 中间随机插入下划线
      } else {
        result += chars[Math.floor(Math.random() * chars.length)];
      }
    }
    return result;
  }, []);

  /** 生成随机用户 ID — 与用户名同规则 */
  const generateUserId = useCallback((): string => {
    return "u_" + generateUsername().slice(0, 6);
  }, [generateUsername]);

  const fetchData = useCallback(async () => {
    try {
      const [cps, usrs, mw] = await Promise.all([
        getCockpits(),
        getUsers().catch(() => []),
        getMiddlewareConfig().catch(() => ({})),
      ]);
      setCockpits(cps.cockpits || []);
      setUsers(usrs);
      setMwConfig(mw);
    } catch {
      toast.error("数据加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 座舱操作
  const handleRegisterCockpit = async () => {
    try {
      await registerCockpit(cockpitForm);
      toast.success("座舱注册成功");
      setShowCockpitForm(false);
      setCockpitForm({ name: "", user_id: "", vehicle_adapter: "mock", theme_color: "#38bdf8" });
      fetchData();
    } catch {
      toast.error("座舱注册失败");
    }
  };

  const handleDeleteCockpit = async (id: string) => {
    if (!confirm(`确认注销座舱 ${id}?`)) return;
    try {
      await deleteCockpit(id);
      toast.success("座舱已注销");
      fetchData();
    } catch {
      toast.error("注销失败");
    }
  };

  // 用户操作
  const handleRegisterUser = async () => {
    try {
      await registerUser(userForm);
      toast.success("用户添加成功");
      setShowUserForm(false);
      setUserForm({ user_id: "", username: "", cockpit_id: "cockpit-01", role: "cockpit_user" });
      fetchData();
    } catch {
      toast.error("用户添加失败");
    }
  };

  // 自动填充用户名和ID
  const handleAutoFillUser = () => {
    const name = generateUsername();
    setUserForm({
      ...userForm,
      user_id: "u_" + name.slice(0, 6),
      username: name,
    });
  };

  // 配置更新
  const handleUpdateMwConfig = async () => {
    try {
      await updateMiddlewareConfig(mwConfig);
      toast.success("配置已更新（热加载生效）");
    } catch {
      toast.error("配置更新失败");
    }
  };

  const tabs = [
    { id: "cockpits" as const, label: "座舱管理", icon: Car },
    { id: "users" as const, label: "用户管理", icon: Users },
    { id: "config" as const, label: "系统配置", icon: Database },
  ];

  // 角色显示名称
  const roleLabels: Record<string, string> = {
    super_admin: "超级管理员",
    cockpit_admin: "座舱管理员",
    cockpit_user: "座舱用户",
    cockpit_viewer: "访客",
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">管理设置</h1>
          <p className="text-sm text-muted-foreground">
            座舱 · 用户 · 系统配置管理
          </p>
        </div>
        <ShieldCheck className="h-6 w-6 text-primary" />
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-2 border-b border-border">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-all border-b-2 ${
                active
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* 座舱管理 */}
      {activeTab === "cockpits" && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          <div className="flex justify-end">
            <Button
              onClick={() => setShowCockpitForm(!showCockpitForm)}
              variant="outline"
            >
              <Plus className="mr-1 h-4 w-4" />
              注册座舱
            </Button>
          </div>

          {showCockpitForm && (
            <Card className="glass">
              <CardContent className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                  <Input
                    placeholder="座舱名称"
                    value={cockpitForm.name}
                    onChange={(e) => setCockpitForm({ ...cockpitForm, name: e.target.value })}
                  />
                  <Input
                    placeholder="绑定用户 ID"
                    value={cockpitForm.user_id}
                    onChange={(e) => setCockpitForm({ ...cockpitForm, user_id: e.target.value })}
                  />
                  <select
                    className="rounded-lg bg-accent/50 px-3 py-2 text-sm outline-none"
                    value={cockpitForm.vehicle_adapter}
                    onChange={(e) => setCockpitForm({ ...cockpitForm, vehicle_adapter: e.target.value })}
                  >
                    <option value="mock">模拟模式</option>
                    <option value="http">HTTP 对接</option>
                    <option value="mcp">MCP 协议</option>
                  </select>
                  <Button onClick={handleRegisterCockpit}>确认注册</Button>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {cockpits.map((c) => (
              <Card key={c.cockpit_id} className="glass">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <div
                          className="h-3 w-3 rounded-full"
                          style={{ backgroundColor: c.theme_color }}
                        />
                        <span className="font-bold">{c.name}</span>
                      </div>
                      <p className="text-xs text-muted-foreground">{c.cockpit_id}</p>
                      <p className="text-xs text-muted-foreground">
                        绑定用户: {c.user_id || "未绑定"}
                      </p>
                      <div className="flex items-center gap-2 pt-1">
                        {c.is_active ? (
                          <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-400">
                            活跃
                          </span>
                        ) : (
                          <span className="rounded bg-red-500/10 px-2 py-0.5 text-[10px] text-red-400">
                            已注销
                          </span>
                        )}
                        <span className="rounded bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-400">
                          {c.subagent_status}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteCockpit(c.cockpit_id)}
                      className="rounded-lg p-2 text-red-400 hover:bg-red-500/10"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </CardContent>
              </Card>
            ))}
            {cockpits.length === 0 && !loading && (
              <div className="col-span-full py-8 text-center text-muted-foreground">
                暂无座舱，请点击"注册座舱"添加
              </div>
            )}
          </div>
        </motion.div>
      )}

      {/* 用户管理 */}
      {activeTab === "users" && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          <div className="flex justify-end">
            <Button
              onClick={() => setShowUserForm(!showUserForm)}
              variant="outline"
            >
              <Plus className="mr-1 h-4 w-4" />
              添加用户
            </Button>
          </div>

          {showUserForm && (
            <Card className="glass">
              <CardContent className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
                  <Input
                    placeholder="用户 ID"
                    value={userForm.user_id}
                    onChange={(e) => setUserForm({ ...userForm, user_id: e.target.value })}
                  />
                  <Input
                    placeholder="用户名 (字母+下划线+数字)"
                    value={userForm.username}
                    onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
                  />
                  <Input
                    placeholder="座舱 ID"
                    value={userForm.cockpit_id}
                    onChange={(e) => setUserForm({ ...userForm, cockpit_id: e.target.value })}
                  />
                  <select
                    className="rounded-lg bg-accent/50 px-3 py-2 text-sm outline-none"
                    value={userForm.role}
                    onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}
                  >
                    <option value="super_admin">超级管理员</option>
                    <option value="cockpit_admin">座舱管理员</option>
                    <option value="cockpit_user">座舱用户</option>
                    <option value="cockpit_viewer">访客</option>
                  </select>
                  <Button variant="outline" onClick={handleAutoFillUser}>
                    <RefreshCw className="mr-1 h-4 w-4" />
                    自动生成
                  </Button>
                  <Button onClick={handleRegisterUser}>确认添加</Button>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  用户名规则: 字母开头，可包含字母、下划线、数字（6-9位）
                </p>
              </CardContent>
            </Card>
          )}

          <Card className="glass">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="p-3 text-left font-medium">用户 ID</th>
                      <th className="p-3 text-left font-medium">用户名</th>
                      <th className="p-3 text-left font-medium">座舱</th>
                      <th className="p-3 text-left font-medium">身份</th>
                      <th className="p-3 text-left font-medium">创建时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.length > 0 ? (
                      users.map((u) => (
                        <tr key={u.user_id} className="border-b border-border/50">
                          <td className="p-3 font-medium">{u.user_id}</td>
                          <td className="p-3">{u.username}</td>
                          <td className="p-3 text-sky-400">{u.cockpit_id || "—"}</td>
                          <td className="p-3">
                            <span
                              className={`rounded px-2 py-0.5 text-xs ${
                                u.role === "super_admin"
                                  ? "bg-purple-500/10 text-purple-400"
                                  : u.role === "cockpit_admin"
                                  ? "bg-sky-500/10 text-sky-400"
                                  : "bg-emerald-500/10 text-emerald-400"
                              }`}
                            >
                              {roleLabels[u.role] || u.role}
                            </span>
                          </td>
                          <td className="p-3 text-xs text-muted-foreground">{u.created_at}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={5} className="p-8 text-center text-muted-foreground">
                          {loading ? "加载中..." : "暂无用户"}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* 系统配置 */}
      {activeTab === "config" && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          <Card className="glass">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5 text-primary" />
                系统运行配置
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground">数据隔离模式</label>
                  <select
                    className="mt-1 w-full rounded-lg bg-accent/50 px-3 py-2 text-sm outline-none"
                    value={mwConfig.isolation_mode || "shared"}
                    onChange={(e) => setMwConfig({ ...mwConfig, isolation_mode: e.target.value })}
                  >
                    <option value="shared">共享模式</option>
                    <option value="isolated">隔离模式</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">巡检间隔（分钟）</label>
                  <Input
                    type="number"
                    value={mwConfig.subagent_check_min || 30}
                    onChange={(e) =>
                      setMwConfig({ ...mwConfig, subagent_check_min: parseInt(e.target.value) })
                    }
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">巡检间隔上限（分钟）</label>
                  <Input
                    type="number"
                    value={mwConfig.subagent_check_max || 60}
                    onChange={(e) =>
                      setMwConfig({ ...mwConfig, subagent_check_max: parseInt(e.target.value) })
                    }
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">限流 QPS</label>
                  <Input
                    type="number"
                    value={mwConfig.rate_limit_qps || 100}
                    onChange={(e) =>
                      setMwConfig({ ...mwConfig, rate_limit_qps: parseInt(e.target.value) })
                    }
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">缓存相似度阈值</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={mwConfig.cache_similarity_threshold || 0.85}
                    onChange={(e) =>
                      setMwConfig({
                        ...mwConfig,
                        cache_similarity_threshold: parseFloat(e.target.value),
                      })
                    }
                  />
                </div>
                <div className="flex items-end">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={mwConfig.mainagent_confirm_enabled ?? true}
                      onChange={(e) =>
                        setMwConfig({ ...mwConfig, mainagent_confirm_enabled: e.target.checked })
                      }
                    />
                    启用主控引擎审核
                  </label>
                </div>
              </div>
              <Button onClick={handleUpdateMwConfig} className="mt-4">
                保存配置（热加载）
              </Button>
            </CardContent>
          </Card>
        </motion.div>
      )}
    </div>
  );
}
