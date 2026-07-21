/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 全局音频管理器 — 跨路由持久化的 Audio 单例
 *
 * 核心问题:
 *   VehiclePanel 组件在路由切换（如 /cockpit → /chat）时被卸载，
 *   useEffect cleanup 会执行 audio.pause() + audio = null，
 *   导致音乐播放中断。用户切回 /cockpit 后需要重新点击播放。
 *
 * 解决方案:
 *   将 HTMLAudioElement 提升到模块级别（单例），生命周期独立于 React 组件。
 *   VehiclePanel 只负责「同步后端媒体状态到音频管理器」，
 *   不再持有 Audio 对象，卸载时不会暂停播放。
 *
 * 设计模式: 与 auth-store.ts 一致的模块级单例 + 监听器模式
 */

// ============================================================
// 类型定义
// ============================================================

/** 后端媒体状态片段 — syncFromMedia() 的入参 */
interface MediaSyncState {
  playing: boolean;
  volume: number;
  track: { url?: string; title?: string } | string | null;
  track_index?: number;
  play_mode?: string; // sequential / single / shuffle
}

/** 音频结束时的回调类型 — 用于自动播放下一首 */
type TrackEndedCallback = () => void;

// ============================================================
// 模块级单例 — Audio 元素只创建一次，永不销毁
// ============================================================

/** 全局唯一的 Audio 元素（懒初始化，仅在浏览器环境创建） */
let _audio: HTMLAudioElement | null = null;

/** 当前播放模式（用于决定 ended 事件的行为） */
let _playMode: string = "sequential";

/** 音频结束回调 */
let _onTrackEnded: TrackEndedCallback | null = null;

/** 上次同步的媒体状态指纹（避免重复同步） */
let _lastMediaKey: string = "";

/** API 基础地址（与 lib/api.ts 保持一致，默认 Go 网关 8080） */
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

/**
 * 获取或创建全局 Audio 元素
 *
 * 在 SSR 环境（typeof window === 'undefined'）下返回 null，
 * 避免服务端渲染报错。
 */
function getAudio(): HTMLAudioElement | null {
  if (typeof window === "undefined") return null;
  if (!_audio) {
    _audio = new Audio();
    _audio.loop = false;
    _audio.addEventListener("ended", () => {
      // 单曲循环模式: audio.loop = true，ended 不会触发，浏览器自动重播
      if (_playMode === "single") return;
      // 列表循环 / 随机播放: 通知外部回调播放下一首
      if (_onTrackEnded) _onTrackEnded();
    });
  }
  return _audio;
}

// ============================================================
// 公开 API
// ============================================================

/**
 * 同步后端媒体状态到音频管理器
 *
 * 使用 JSON.stringify 做深度比较，如果媒体关键状态没变化则跳过，
 * 避免组件重渲染时重复操作音频导致中断。
 *
 * @param media - 后端返回的媒体状态
 */
export function syncAudioFromMedia(media: MediaSyncState | undefined | null) {
  if (!media) return;

  const audio = getAudio();
  if (!audio) return;

  // 计算媒体状态指纹，与上次比较
  const mediaKey = JSON.stringify({
    playing: media.playing,
    track: media.track,
    track_index: media.track_index,
    volume: media.volume,
  });

  if (mediaKey === _lastMediaKey) return;
  _lastMediaKey = mediaKey;

  // 同步播放模式
  if (media.play_mode) {
    _playMode = media.play_mode;
    audio.loop = (media.play_mode === "single");
  }

  // 构建音频 URL
  const trackUrl = (media.track as any)?.url
    ? `${API_BASE}${(media.track as any).url}`
    : `${API_BASE}/audio/music/track_${String((media.track_index ?? 0) + 1).padStart(2, "0")}.wav`;

  if (media.playing) {
    if (audio.src !== trackUrl) {
      audio.src = trackUrl;
    }
    audio.volume = Math.min(1, (media.volume || 18) / 30);
    audio.play().catch(() => {
      // 浏览器自动播放策略可能阻止，静默处理
    });
  } else {
    audio.pause();
  }
}

/**
 * 设置音频结束回调（用于自动播放下一首）
 *
 * VehiclePanel 在挂载时设置此回调，卸载时清除。
 * 注意: 即使 VehiclePanel 卸载，音频仍继续播放；
 * 但自动播放下一首的功能在 VehiclePanel 不存在时无法触发
 * （因为没有组件来发送 vehicle_media next 命令）。
 * 这是合理的行为 — 用户切到其他页面时不需要自动切歌。
 */
export function setOnTrackEnded(callback: TrackEndedCallback | null) {
  _onTrackEnded = callback;
}

/**
 * 获取当前是否正在播放
 */
export function isAudioPlaying(): boolean {
  const audio = getAudio();
  return audio ? !audio.paused : false;
}

/**
 * 手动暂停音频（仅在用户主动操作时调用）
 */
export function pauseAudio() {
  const audio = getAudio();
  if (audio) audio.pause();
}

/**
 * 手动恢复播放
 */
export function resumeAudio() {
  const audio = getAudio();
  if (audio) audio.play().catch(() => {});
}

/**
 * 设置音量（0-1）
 */
export function setAudioVolume(volume: number) {
  const audio = getAudio();
  if (audio) audio.volume = Math.min(1, Math.max(0, volume));
}

/**
 * 重置媒体状态指纹
 *
 * 当座舱切换或强制刷新状态时调用，确保下次 syncAudioFromMedia 能正常同步。
 */
export function resetAudioSyncKey() {
  _lastMediaKey = "";
}
