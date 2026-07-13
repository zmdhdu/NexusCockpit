/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 车控状态刷新事件总线
 *
 * 当语音助手或文字输入触发了车控命令后，通过此事件总线通知
 * VehiclePanel 组件重新拉取车辆状态，实现 UI 联动刷新。
 *
 * 使用方式:
 *   - VoiceAssistantBar: 命令执行后调用 emitVehicleRefresh()
 *   - VehiclePanel: 通过 onVehicleRefresh() 订阅刷新事件
 */

type VehicleRefreshListener = () => void;

const listeners = new Set<VehicleRefreshListener>();

/** 触发车控状态刷新通知 */
export function emitVehicleRefresh() {
  listeners.forEach((fn) => fn());
}

/** 订阅车控状态刷新事件，返回取消订阅函数 */
export function onVehicleRefresh(listener: VehicleRefreshListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
