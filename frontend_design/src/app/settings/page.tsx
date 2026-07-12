"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Settings,
  Mic,
  Upload,
  Fingerprint,
  CheckCircle2,
  AlertCircle,
  User,
  Volume2,
  Lock,
  LogIn,
  LogOut,
} from "lucide-react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useAuth } from "@/stores/auth-store";
import {
  getVoiceprintStatus,
  enrollVoiceprint,
  verifyVoiceprint,
  deleteVoiceprint,
  changePassword,
  login as apiLogin,
  logout as apiLogout,
} from "@/lib/api";
import type { VoiceprintStatus } from "@/types";

/**
 * 个人设置页 — 面向终端用户
 *
 * 展示内容:
 *   1. 个人信息（用户ID、当前座舱、角色）
 *   2. 声纹注册 — 录制/上传音频完成注册
 *   3. 声纹验证 — 测试声纹识别是否生效
 *   4. 已注册声纹列表
 *
 * 不展示任何技术名词，纯粹面向用户个人配置。
 */
export default function SettingsPage() {
  const { userId, role, cockpitId, isAuthenticated, logout: authLogout } = useAuth();
  const [voiceprintStatus, setVoiceprintStatus] = useState<VoiceprintStatus | any>(null);
  const [loading, setLoading] = useState(true);

  // 声纹注册
  const [enrollFile, setEnrollFile] = useState<File | null>(null);
  const [enrolling, setEnrolling] = useState(false);

  // 声纹验证
  const [verifyFile, setVerifyFile] = useState<File | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<any>(null);

  // 修改密码
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);

  // 登录表单
  const [loginUserId, setLoginUserId] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const vp = await getVoiceprintStatus(cockpitId).catch(() => null);
      setVoiceprintStatus(vp);
    } catch {
      // 静默处理
    } finally {
      setLoading(false);
    }
  }, [cockpitId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 声纹注册
  const handleEnroll = async () => {
    if (!enrollFile) {
      toast.error("请先选择音频文件");
      return;
    }
    setEnrolling(true);
    try {
      const result = await enrollVoiceprint(cockpitId, userId || "default", enrollFile);
      toast.success("声纹注册成功", {
        description: result.message || "您现在可以通过语音快速登录",
      });
      setEnrollFile(null);
      fetchData();
    } catch {
      toast.error("声纹注册失败", {
        description: "请确保音频清晰且时长不少于3秒",
      });
    } finally {
      setEnrolling(false);
    }
  };

  // 声纹验证
  const handleVerify = async () => {
    if (!verifyFile) {
      toast.error("请先选择音频文件");
      return;
    }
    setVerifying(true);
    setVerifyResult(null);
    try {
      const result = await verifyVoiceprint(cockpitId, verifyFile);
      setVerifyResult(result);
      if (result.verified) {
        toast.success("验证通过", {
          description: `已识别为用户: ${result.user_id}`,
        });
      } else {
        toast.warning("验证未通过", {
          description: result.message || "请重新注册声纹后重试",
        });
      }
    } catch {
      toast.error("声纹验证失败");
    } finally {
      setVerifying(false);
    }
  };

  // 删除声纹
  const handleDeleteVoiceprint = async (uid: string) => {
    if (!confirm(`确认删除用户 ${uid} 的声纹数据？`)) return;
    try {
      await deleteVoiceprint(uid, cockpitId);
      toast.success("声纹已删除");
      fetchData();
    } catch {
      toast.error("删除失败");
    }
  };

  // 修改密码
  const handleChangePassword = async () => {
    if (!newPassword || newPassword.length < 6) {
      toast.error("新密码至少 6 位");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("两次输入的密码不一致");
      return;
    }
    setChangingPassword(true);
    try {
      await changePassword(oldPassword, newPassword);
      toast.success("密码修改成功");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch {
      toast.error("密码修改失败");
    } finally {
      setChangingPassword(false);
    }
  };

  // 登录
  const handleLogin = async () => {
    if (!loginUserId.trim()) {
      toast.error("请输入用户 ID");
      return;
    }
    setLoggingIn(true);
    try {
      await apiLogin(loginUserId.trim(), loginPassword);
      toast.success("登录成功");
      setLoginUserId("");
      setLoginPassword("");
    } catch (e: any) {
      toast.error("登录失败", { description: e?.message || "请检查用户 ID 和密码" });
    } finally {
      setLoggingIn(false);
    }
  };

  // 退出登录
  const handleLogout = async () => {
    await apiLogout();
    authLogout();
    toast.success("已退出登录");
  };

  // 角色显示名称
  const roleLabels: Record<string, string> = {
    super_admin: "管理员",
    cockpit_admin: "座舱管理员",
    cockpit_user: "座舱用户",
    cockpit_viewer: "访客",
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">个人设置</h1>
        <p className="text-sm text-muted-foreground">
          管理您的个人信息与声纹数据
        </p>
      </div>

      {/* 个人信息 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5 text-primary" />
              个人信息
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-lg bg-accent/30 p-4">
                <p className="text-xs text-muted-foreground mb-1">用户账号</p>
                <p className="text-sm font-medium">{userId || "未登录"}</p>
              </div>
              <div className="rounded-lg bg-accent/30 p-4">
                <p className="text-xs text-muted-foreground mb-1">当前座舱</p>
                <p className="text-sm font-medium">{cockpitId}</p>
              </div>
              <div className="rounded-lg bg-accent/30 p-4">
                <p className="text-xs text-muted-foreground mb-1">身份</p>
                <p className="text-sm font-medium">{roleLabels[role] || role}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* 登录/退出 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {isAuthenticated ? (
                <LogOut className="h-5 w-5 text-primary" />
              ) : (
                <LogIn className="h-5 w-5 text-primary" />
              )}
              {isAuthenticated ? "账号管理" : "登录"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isAuthenticated ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                    <User className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{userId}</p>
                    <p className="text-xs text-muted-foreground">
                      {roleLabels[role] || role} · {cockpitId}
                    </p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  onClick={handleLogout}
                  className="text-red-400 hover:bg-red-500/10"
                >
                  <LogOut className="mr-1 h-4 w-4" />
                  退出登录
                </Button>
              </div>
            ) : (
              <div className="max-w-md space-y-3">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-muted-foreground">
                    用户 ID
                  </label>
                  <Input
                    value={loginUserId}
                    onChange={(e) => setLoginUserId(e.target.value)}
                    placeholder="输入您的用户 ID"
                    className="bg-background/50"
                    onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-muted-foreground">
                    密码（可选）
                  </label>
                  <Input
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="开发环境可留空"
                    className="bg-background/50"
                    onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                  />
                </div>
                <Button
                  onClick={handleLogin}
                  disabled={loggingIn || !loginUserId.trim()}
                  className="w-full"
                >
                  {loggingIn ? "登录中..." : "登录"}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* 声纹管理 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 声纹注册 */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
        >
          <Card className="glass h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mic className="h-5 w-5 text-primary" />
                声纹注册
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                上传一段不少于3秒的语音，完成声纹注册后即可通过语音快速登录座舱。
              </p>
              <div className="flex items-center gap-2">
                <label className="flex-1 cursor-pointer rounded-lg border border-dashed border-border px-4 py-3 text-center text-sm text-muted-foreground hover:border-primary">
                  <Upload className="mx-auto mb-1 h-4 w-4" />
                  {enrollFile ? enrollFile.name : "选择音频文件 (wav)"}
                  <input
                    type="file"
                    accept="audio/wav,audio/*"
                    className="hidden"
                    onChange={(e) => setEnrollFile(e.target.files?.[0] || null)}
                  />
                </label>
                <Button
                  onClick={handleEnroll}
                  disabled={!enrollFile || enrolling}
                  className="px-6"
                >
                  {enrolling ? "注册中..." : "注册"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* 声纹验证 */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
        >
          <Card className="glass h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Fingerprint className="h-5 w-5 text-primary" />
                声纹验证
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                上传一段语音进行验证，测试声纹识别是否正常工作。
              </p>
              <div className="flex items-center gap-2">
                <label className="flex-1 cursor-pointer rounded-lg border border-dashed border-border px-4 py-3 text-center text-sm text-muted-foreground hover:border-primary">
                  <Upload className="mx-auto mb-1 h-4 w-4" />
                  {verifyFile ? verifyFile.name : "选择音频文件 (wav)"}
                  <input
                    type="file"
                    accept="audio/wav,audio/*"
                    className="hidden"
                    onChange={(e) => setVerifyFile(e.target.files?.[0] || null)}
                  />
                </label>
                <Button
                  onClick={handleVerify}
                  disabled={!verifyFile || verifying}
                  className="px-6"
                >
                  {verifying ? "验证中..." : "验证"}
                </Button>
              </div>
              {verifyResult && (
                <div
                  className={`rounded-lg p-3 ${
                    verifyResult.verified
                      ? "bg-emerald-500/10"
                      : "bg-red-500/10"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {verifyResult.verified ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    ) : (
                      <AlertCircle className="h-4 w-4 text-red-400" />
                    )}
                    <span className="text-sm font-medium">
                      {verifyResult.verified
                        ? `验证通过: ${verifyResult.user_id}`
                        : "验证未通过"}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    相似度: {((verifyResult.similarity || 0) * 100).toFixed(1)}%
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* 已注册声纹 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Volume2 className="h-5 w-5 text-primary" />
              已注册声纹
            </CardTitle>
          </CardHeader>
          <CardContent>
            {voiceprintStatus?.users && voiceprintStatus.users.length > 0 ? (
              <div className="space-y-2">
                {voiceprintStatus.users.map((u: any) => (
                  <div
                    key={u.user_id}
                    className="flex items-center justify-between rounded-lg bg-accent/30 px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
                        <User className="h-4 w-4 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm font-medium">{u.user_id}</p>
                        <p className="text-xs text-muted-foreground">
                          注册次数: {u.enroll_count}
                          {u.completed && (
                            <span className="ml-2 text-emerald-400">已完成</span>
                          )}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteVoiceprint(u.user_id)}
                      className="rounded-lg px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10"
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center text-sm text-muted-foreground">
                {loading ? "加载中..." : "暂无已注册的声纹"}
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* 修改密码 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
      >
        <Card className="glass">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lock className="h-5 w-5 text-primary" />
              修改密码
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-w-md space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-muted-foreground">
                  旧密码
                </label>
                <Input
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  placeholder="输入当前密码"
                  className="bg-background/50"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-muted-foreground">
                  新密码
                </label>
                <Input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="至少 6 位"
                  className="bg-background/50"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-muted-foreground">
                  确认新密码
                </label>
                <Input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="再次输入新密码"
                  className="bg-background/50"
                />
              </div>
              <Button
                onClick={handleChangePassword}
                disabled={changingPassword || !newPassword || !confirmPassword}
                className="w-full"
              >
                {changingPassword ? "修改中..." : "确认修改"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
