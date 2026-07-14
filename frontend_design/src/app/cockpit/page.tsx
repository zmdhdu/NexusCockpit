/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { VehiclePanel } from "@/components/vehicle/vehicle-panel";
import { VoiceAssistantBar } from "@/components/vehicle/voice-assistant-bar";

/**
 * 座舱控制页 — 用户主界面
 *
 * 这是普通用户进入系统后看到的第一屏:
 *   - 顶部: 语音助手快捷输入栏
 *   - 下方: 车控面板（空调、座椅、音乐、导航、车窗）
 *
 * 不展示任何技术名词，纯粹面向终端用户的操控界面。
 * 如果管理员访问此页面，也可以正常使用（测试/巡检用途）。
 */
export default function CockpitPage() {
  return (
    <div className="space-y-4">
      {/* 页面标题 */}
      <div>
        <h1 className="text-2xl font-bold">座舱控制</h1>
        <p className="text-sm text-muted-foreground">
          语音控制 · 快捷操作 · 实时状态
        </p>
      </div>

      {/* 语音助手栏 — 置顶方便用户快速操作 */}
      <VoiceAssistantBar />

      {/* 车控面板 */}
      <VehiclePanel />
    </div>
  );
}
