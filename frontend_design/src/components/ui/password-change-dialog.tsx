/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { useState, useEffect, useCallback } from "react";
import { Lock, Phone, KeyRound, ShieldCheck } from "lucide-react";
import { Dialog, DialogHeader, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import {
  changePassword,
  sendVerifyCode,
  changePasswordByCode,
  resetUserPassword,
} from "@/lib/api";

interface PasswordChangeDialogProps {
  /** 是否打开 */
  open: boolean;
  /** 关闭回调 */
  onOpenChange: (open: boolean) => void;
  /**
   * 模式:
   *   - "self"       用户修改自己的密码（调用 /auth/change-password）
   *   - "admin_reset" 管理员重置他人密码（调用 /settings/users/:id/password）
   */
  mode?: "self" | "admin_reset";
  /** 管理员重置模式下的目标用户 ID */
  targetUserId?: string;
  /** 管理员重置模式下的目标用户显示名 */
  targetUserLabel?: string;
}

/**
 * 密码修改弹窗 — 支持两种验证方式
 *
 * 方式一: 旧密码验证（输入旧密码 + 新密码 + 确认密码）
 * 方式二: 手机号验证码（忘记旧密码时，通过手机号 + 验证码修改）
 *
 * 参考市面上常见的密码修改交互:
 *   - 点击按钮触发弹窗
 *   - Tab 切换验证方式
 *   - 手机验证码带倒计时
 */
export function PasswordChangeDialog({
  open,
  onOpenChange,
  mode = "self",
  targetUserId,
  targetUserLabel,
}: PasswordChangeDialogProps) {
  const [tab, setTab] = useState<"password" | "phone">("password");

  // 密码验证模式
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // 手机验证码模式
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [phoneNewPassword, setPhoneNewPassword] = useState("");
  const [phoneConfirmPassword, setPhoneConfirmPassword] = useState("");

  // 倒计时 & 提交状态
  const [countdown, setCountdown] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);

  // 弹窗关闭时重置所有状态
  const resetState = useCallback(() => {
    setTab("password");
    setOldPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setPhone("");
    setCode("");
    setPhoneNewPassword("");
    setPhoneConfirmPassword("");
    setCountdown(0);
  }, []);

  useEffect(() => {
    if (!open) resetState();
  }, [open, resetState]);

  // 倒计时效果
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  // 发送验证码
  const handleSendCode = async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      toast.error("请输入正确的手机号");
      return;
    }
    setSendingCode(true);
    try {
      const res = await sendVerifyCode(phone);
      if (res.dev_code) {
        // 开发模式下后端返回验证码，自动填入方便测试
        setCode(res.dev_code);
        toast.success("验证码已发送（开发模式已自动填入）");
      } else {
        toast.success("验证码已发送至您的手机");
      }
      setCountdown(60);
    } catch {
      toast.error("验证码发送失败");
    } finally {
      setSendingCode(false);
    }
  };

  // 提交: 密码验证模式
  const handleSubmitByPassword = async () => {
    if (mode === "self" && !oldPassword) {
      toast.error("请输入旧密码");
      return;
    }
    if (newPassword.length < 6) {
      toast.error("新密码至少 6 位");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("两次输入的密码不一致");
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "self") {
        await changePassword(oldPassword, newPassword);
      } else {
        // 管理员重置: 调用 resetUserPassword
        await resetUserPassword(targetUserId!, { password: newPassword });
      }
      toast.success("密码修改成功");
      onOpenChange(false);
    } catch {
      toast.error("密码修改失败");
    } finally {
      setSubmitting(false);
    }
  };

  // 提交: 手机验证码模式
  const handleSubmitByPhone = async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      toast.error("请输入正确的手机号");
      return;
    }
    if (code.length !== 6) {
      toast.error("请输入 6 位验证码");
      return;
    }
    if (phoneNewPassword.length < 6) {
      toast.error("新密码至少 6 位");
      return;
    }
    if (phoneNewPassword !== phoneConfirmPassword) {
      toast.error("两次输入的密码不一致");
      return;
    }

    setSubmitting(true);
    try {
      await changePasswordByCode(phone, code, phoneNewPassword);
      toast.success("密码修改成功");
      onOpenChange(false);
    } catch {
      toast.error("密码修改失败，请检查验证码是否正确");
    } finally {
      setSubmitting(false);
    }
  };

  const title =
    mode === "admin_reset"
      ? `重置 ${targetUserLabel || targetUserId || ""} 的密码`
      : "修改密码";

  const description =
    mode === "admin_reset"
      ? "请选择验证方式重置该用户的密码"
      : "请选择验证方式修改您的密码";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <div className="w-full max-w-md rounded-lg bg-card p-6 shadow-lg">
        {/* 头部 */}
        <div className="mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Lock className="h-5 w-5 text-primary" />
            {title}
          </h3>
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        </div>

        {/* Tab 切换 */}
        <div className="mb-5 flex gap-2 rounded-lg bg-accent/30 p-1">
          <button
            onClick={() => setTab("password")}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-all ${
              tab === "password"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <KeyRound className="mr-1.5 inline h-4 w-4" />
            密码验证
          </button>
          <button
            onClick={() => setTab("phone")}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-all ${
              tab === "phone"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Phone className="mr-1.5 inline h-4 w-4" />
            手机验证码
          </button>
        </div>

        {/* 密码验证模式 */}
        {tab === "password" && (
          <div className="space-y-4">
            {mode === "self" && (
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
            )}
            {mode === "admin_reset" && (
              <div className="rounded-lg bg-amber-500/10 p-3 text-xs text-amber-400">
                <ShieldCheck className="mr-1 inline h-3.5 w-3.5" />
                管理员重置模式：直接设置新密码，无需旧密码
              </div>
            )}
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
                onKeyDown={(e) =>
                  e.key === "Enter" && handleSubmitByPassword()
                }
              />
            </div>
          </div>
        )}

        {/* 手机验证码模式 */}
        {tab === "phone" && (
          <div className="space-y-4">
            <div className="rounded-lg bg-sky-500/10 p-3 text-xs text-sky-400">
              <Phone className="mr-1 inline h-3.5 w-3.5" />
              忘记旧密码？通过手机号验证码修改密码
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">
                手机号
              </label>
              <Input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="请输入绑定的手机号"
                className="bg-background/50"
                maxLength={11}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">
                验证码
              </label>
              <div className="flex gap-2">
                <Input
                  type="text"
                  value={code}
                  onChange={(e) =>
                    setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                  }
                  placeholder="6 位验证码"
                  className="bg-background/50 flex-1"
                  maxLength={6}
                />
                <Button
                  variant="outline"
                  onClick={handleSendCode}
                  disabled={sendingCode || countdown > 0 || phone.length !== 11}
                  className="whitespace-nowrap"
                >
                  {countdown > 0 ? `${countdown}s` : sendingCode ? "发送中" : "获取验证码"}
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">
                新密码
              </label>
              <Input
                type="password"
                value={phoneNewPassword}
                onChange={(e) => setPhoneNewPassword(e.target.value)}
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
                value={phoneConfirmPassword}
                onChange={(e) => setPhoneConfirmPassword(e.target.value)}
                placeholder="再次输入新密码"
                className="bg-background/50"
                onKeyDown={(e) =>
                  e.key === "Enter" && handleSubmitByPhone()
                }
              />
            </div>
          </div>
        )}

        {/* 底部按钮 */}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={tab === "password" ? handleSubmitByPassword : handleSubmitByPhone}
            disabled={
              submitting ||
              (tab === "password"
                ? newPassword.length < 6 || newPassword !== confirmPassword
                : phone.length !== 11 || code.length !== 6 || phoneNewPassword.length < 6 || phoneNewPassword !== phoneConfirmPassword)
            }
          >
            {submitting ? "修改中..." : "确认修改"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
