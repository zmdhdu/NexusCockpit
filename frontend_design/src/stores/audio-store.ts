/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 全局音频管理器 — 跨路由持久化的 Audio 单例
 *
 * 核心设计原则:
 *   1. HTMLAudioElement 提升到模块级别（单例），生命周期独立于 React 组件。
 *      VehiclePanel 卸载时不会暂停播放，切回后音乐继续。
 *
 *   2. 分离关注点: 轨道 URL / 播放状态 / 音量 三者独立同步。
 *      - 只有轨道 URL 变化时才重设 audio.src（避免从头播放）
 *      - 只有播放状态变化时才 play/pause（避免重复调用 play() 导致中断）
 *      - 音量始终非破坏性更新（不触发 src 重载或 play/pause）
 *
 *   3. TTS 语音播报时自动暂停音乐，播报结束后断点续播。
 *      用户在 TTS 期间手动暂停音乐则不会自动恢复。
 *
 *   4. 座舱切换时只有 cockpitId 真正变化才重置同步缓存，
 *      避免组件 remount（路由切换回来）时误重置导致音乐重启。
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

/** 当前已加载的轨道 URL — 只有变化时才重设 audio.src */
let _currentTrackUrl: string = "";

/** 上次同步的播放+轨道指纹（不含音量，避免音量变化触发完整重同步） */
let _lastSyncKey: string = "";

/** 当前座舱 ID — 用于判断座舱是否真正切换 */
let _currentCockpitId: string = "";

/** 后端最近的播放状态 — TTS 恢复时参考此值决定是否续播 */
let _backendPlaying: boolean = false;

/** TTS 暂停标志 — 为 true 时 syncAudioFromMedia 不改变播放状态 */
let _pausedByTTS: boolean = false;

/** TTS 暂停计数器 — 支持多次 speak() 嵌套调用 */
let _ttsPauseCount: number = 0;

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

/**
 * 根据媒体状态构建轨道 URL
 */
function buildTrackUrl(media: MediaSyncState): string {
  const trackObj = media.track as any;
  if (trackObj?.url) {
    return `${API_BASE}${trackObj.url}`;
  }
  return `${API_BASE}/audio/music/track_${String((media.track_index ?? 0) + 1).padStart(2, "0")}.wav`;
}

// ============================================================
// 公开 API
// ============================================================

/**
 * 同步后端媒体状态到音频管理器
 *
 * 分层同步策略（避免不必要的音频中断）:
 *   1. 音量 — 始终非破坏性更新（只设 audio.volume，不影响 src/play）
 *   2. 播放模式 — 始终更新（audio.loop 是非破坏性属性）
 *   3. 轨道 + 播放状态 — 仅在指纹变化时才操作 src/play
 *
 * @param media - 后端返回的媒体状态
 */
export function syncAudioFromMedia(media: MediaSyncState | undefined | null) {
  if (!media) return;

  const audio = getAudio();
  if (!audio) return;

  // 记录后端播放状态（TTS 恢复时参考）
  _backendPlaying = !!media.playing;

  // ── 层 1: 播放模式（非破坏性，始终更新）──
  if (media.play_mode) {
    _playMode = media.play_mode;
    audio.loop = (media.play_mode === "single");
  }

  // ── 层 2: 音量（非破坏性，始终更新）──
  audio.volume = Math.min(1, (media.volume || 18) / 30);

  // 构建轨道 URL
  const trackUrl = buildTrackUrl(media);

  // ── TTS 暂停期间: 只更新轨道 URL，不改变播放状态 ──
  if (_pausedByTTS) {
    if (trackUrl !== _currentTrackUrl) {
      _currentTrackUrl = trackUrl;
      audio.src = trackUrl;
    }
    // 更新指纹，避免 TTS 结束后重复同步
    _lastSyncKey = JSON.stringify({
      playing: media.playing,
      track: media.track,
      track_index: media.track_index,
    });
    return;
  }

  // ── 层 3: 轨道 + 播放状态（仅在指纹变化时操作）──
  const syncKey = JSON.stringify({
    playing: media.playing,
    track: media.track,
    track_index: media.track_index,
  });

  if (syncKey === _lastSyncKey) return; // 播放+轨道未变，跳过
  _lastSyncKey = syncKey;

  if (media.playing) {
    if (trackUrl !== _currentTrackUrl) {
      // 轨道变化 — 设置新 src 并播放
      _currentTrackUrl = trackUrl;
      audio.src = trackUrl;
      audio.play().catch(() => {
        // 浏览器自动播放策略可能阻止，静默处理
      });
    } else {
      // 同一轨道 — 仅在暂停状态下恢复播放，已在播放则不干预
      if (audio.paused) {
        audio.play().catch(() => {});
      }
    }
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
 * 重置媒体同步缓存
 *
 * 当座舱真正切换时调用，确保新座舱的媒体状态被强制同步。
 * 内部通过 cockpitId 判断：只有座舱 ID 真正变化才执行重置，
 * 避免组件 remount（路由切回）时误重置导致音乐从头播放。
 *
 * @param cockpitId - 当前座舱 ID，传入后会与上次比较
 */
export function resetAudioSyncKey(cockpitId?: string) {
  // 只有座舱真正切换才重置
  if (cockpitId !== undefined && cockpitId === _currentCockpitId) return;
  _currentCockpitId = cockpitId || "";
  _lastSyncKey = "";
  _currentTrackUrl = "";
}

// ============================================================
// TTS 语音播报集成 — 自动暂停/断点续播
// ============================================================

/**
 * TTS 开始播报前调用 — 暂停音乐播放
 *
 * 使用计数器支持多次 speak() 嵌套调用:
 *   - 第一次调用: 暂停音乐，设置 _pausedByTTS 标志
 *   - 后续调用: 仅增加计数，不重复暂停
 *
 * 音乐恢复时机由 resumeAfterTTS() 的计数器归零决定。
 */
export function pauseForTTS() {
  const audio = getAudio();
  if (!audio) return;

  if (_ttsPauseCount === 0) {
    _pausedByTTS = true;
    if (!audio.paused) {
      audio.pause(); // 断点暂停，currentTime 保留
    }
  }
  _ttsPauseCount++;
}

/**
 * TTS 播报结束后调用 — 断点续播音乐
 *
 * 计数器归零时恢复播放，条件:
 *   1. 没有更多 TTS 在排队（_ttsPauseCount === 0）
 *   2. 后端状态仍为 playing（用户没在 TTS 期间手动暂停）
 *
 * 这样实现了「语音播报时音乐自动暂停，播报结束后从断点继续」。
 */
export function resumeAfterTTS() {
  _ttsPauseCount = Math.max(0, _ttsPauseCount - 1);
  if (_ttsPauseCount > 0) return; // 还有 TTS 在播报

  _pausedByTTS = false;

  // 只有后端仍认为在播放时才恢复（用户可能在 TTS 期间手动暂停了）
  if (_backendPlaying) {
    const audio = getAudio();
    if (audio && audio.paused) {
      audio.play().catch(() => {});
    }
  }
}
