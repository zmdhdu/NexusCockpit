/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * TTS 语音合成引擎 — 分句播放 + 全局播放状态机
 *
 * 核心特性:
 *   - 按标点智能分句，逐句播报（替代整段一次性播放）
 *   - 全局播放状态机：playing / paused / stopped
 *   - 支持暂停、断点续播、单句重放、整条重放、终止播放
 *   - 用户随时可打断语音播报，优先用户操作
 *   - 严格绑定校验：仅传入已通过 Reviewer 终审的文本
 *   - 代际计数器防止旧 utterance 回调干扰新播放
 *   - Chrome speechSynthesis 保活机制防止长时间播放冻结
 *
 * 音乐联动:
 *   朗读开始前自动暂停座舱音乐（保留播放进度），
 *   朗读结束后从断点恢复播放。
 *   用户在朗读期间手动暂停音乐则不会自动恢复。
 *
 * 使用方式:
 *   import { speakSentences, pausePlayback, resumePlayback,
 *            replayPlayback, stopPlayback, getPlaybackState } from "@/lib/tts";
 *
 *   // 播放（传入已校验的完整文本）
 *   speakSentences(text);
 *   // 暂停
 *   pausePlayback();
 *   // 断点续播
 *   resumePlayback();
 *   // 整条重放
 *   replayPlayback();
 *   // 终止播放
 *   stopPlayback();
 */

import { pauseForTTS, resumeAfterTTS } from "@/stores/audio-store";

// ============================================================
// 类型定义
// ============================================================

/** 播放状态 */
export type PlaybackState = "idle" | "playing" | "paused" | "stopped";

/** 播放状态变更回调 */
type StateChangeListener = (state: PlaybackState, currentIndex: number, total: number) => void;

// ============================================================
// 全局播放状态机
// ============================================================

/** 当前播放状态 */
let _state: PlaybackState = "idle";

/** 分句后的句子列表 */
let _sentences: string[] = [];

/** 当前播放句子的索引 */
let _currentIndex: number = 0;

/** 当前播放关联的消息 ID（用于前端 UI 关联） */
let _messageId: string = "";

/**
 * 代际计数器 — 每次 speakSentences / replayPlayback 递增
 * 旧 utterance 的 onend / onerror 回调携带旧 generation，
 * 与当前 generation 不匹配时直接丢弃，防止竞态干扰。
 */
let _generation: number = 0;

/** 状态变更监听器列表 */
const _listeners: Set<StateChangeListener> = new Set();

/** 当前正在播放的 utterance（用于 pause/resume） */
let _currentUtterance: SpeechSynthesisUtterance | null = null;

/**
 * Chrome speechSynthesis 保活定时器
 *
 * Chrome 已知 bug：连续播放超过 ~15 秒后 speechSynthesis 会停止触发事件，
 * 导致 onend 永远不回调，播放卡死。通过周期性 pause→resume 保活。
 */
let _keepAliveTimer: ReturnType<typeof setInterval> | null = null;

// ============================================================
// 工具函数
// ============================================================

/** 是否支持语音合成 */
export function isTTSSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/**
 * 按标点智能分句 — 将完整文本按中文/英文标点切分为句子
 *
 * 切分标点: 。！？；!?;（句子级）
 * 保留标点在句尾，过滤空句。
 */
export function splitIntoSentences(text: string): string[] {
  if (!text) return [];

  // 清理 markdown 标记
  const cleanText = text
    .replace(/```[\s\S]*?```/g, "代码块")
    .replace(/[*_#`~]/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .trim();

  if (!cleanText) return [];

  // 按句子级标点分句，保留标点
  const sentences = cleanText
    .split(/(?<=[。！？；!?;])\s*/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

  // 如果只有一句或没有标点切分，直接返回整段
  return sentences;
}

/** 获取当前播放状态 */
export function getPlaybackState(): PlaybackState {
  return _state;
}

/** 获取当前播放的句子索引和总数 */
export function getPlaybackProgress(): { currentIndex: number; total: number } {
  return { currentIndex: _currentIndex, total: _sentences.length };
}

/** 获取当前播放关联的消息 ID */
export function getPlaybackMessageId(): string {
  return _messageId;
}

/** 注册状态变更监听器 */
export function onPlaybackStateChange(listener: StateChangeListener): () => void {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

/** 通知所有监听器状态变更 */
function _notifyStateChange(): void {
  for (const listener of _listeners) {
    listener(_state, _currentIndex, _sentences.length);
  }
}

/** 设置播放状态并通知监听器 */
function _setState(newState: PlaybackState): void {
  _state = newState;
  _notifyStateChange();
}

// ============================================================
// Chrome speechSynthesis 保活机制
// ============================================================

/** 启动保活定时器 — 每 10 秒 pause→resume 防止 Chrome 冻结 */
function _startKeepAlive(): void {
  _stopKeepAlive();
  _keepAliveTimer = setInterval(() => {
    if (!isTTSSupported()) return;
    if (_state === "playing" && window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
      // Chrome bug workaround: 周期性 pause→resume 保持事件触发
      window.speechSynthesis.pause();
      window.speechSynthesis.resume();
    }
  }, 10000);
}

/** 停止保活定时器 */
function _stopKeepAlive(): void {
  if (_keepAliveTimer !== null) {
    clearInterval(_keepAliveTimer);
    _keepAliveTimer = null;
  }
}

// ============================================================
// 核心：创建并播放单个句子的 utterance
// ============================================================

/**
 * 创建一个 SpeechSynthesisUtterance
 */
function _createUtterance(text: string): SpeechSynthesisUtterance {
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  utterance.volume = 0.8;

  // 尝试使用中文语音
  const voices = window.speechSynthesis.getVoices();
  const zhVoice = voices.find((v) => v.lang.startsWith("zh"));
  if (zhVoice) {
    utterance.voice = zhVoice;
  }

  return utterance;
}

/**
 * 播放指定索引的句子
 *
 * @param index 句子索引
 * @param gen 调用时的代际计数器值，用于检测是否是过期的回调
 */
function _playSentence(index: number, gen: number): void {
  // 代际检查：如果是过期的回调，直接丢弃
  if (gen !== _generation) return;

  if (!isTTSSupported() || index < 0 || index >= _sentences.length) {
    // 所有句子播放完毕
    _currentUtterance = null;
    _stopKeepAlive();
    _setState("idle");
    // 恢复音乐
    resumeAfterTTS();
    return;
  }

  _currentIndex = index;
  _notifyStateChange();

  const text = _sentences[index];
  const utterance = _createUtterance(text);
  _currentUtterance = utterance;

  utterance.onend = () => {
    // 代际检查：丢弃过期回调
    if (gen !== _generation) return;

    _currentUtterance = null;
    // 如果状态是 stopped / idle，不继续播放下一句
    if (_state === "stopped" || _state === "idle") {
      return;
    }
    // 播放下一句
    if (_state === "playing") {
      _playSentence(index + 1, gen);
    }
  };

  utterance.onerror = (event) => {
    // 代际检查：丢弃过期回调
    if (gen !== _generation) return;

    _currentUtterance = null;
    console.warn(`TTS sentence ${index} error:`, event?.error || event);
    if (_state === "stopped" || _state === "idle") {
      return;
    }
    // 出错时跳过当前句，继续下一句
    if (_state === "playing") {
      _playSentence(index + 1, gen);
    }
  };

  window.speechSynthesis.speak(utterance);
}

// ============================================================
// 公共 API
// ============================================================

/**
 * 分句播放文本 — 按标点分句，逐句播报
 *
 * 仅在收到 done 事件（Reviewer 终审通过）后调用此函数，
 * 确保未校验内容不进入 TTS 播放。
 *
 * @param text 已通过全链路校验的完整回复文本
 * @param messageId 关联的消息 ID（用于前端 UI 播放状态关联）
 */
export function speakSentences(text: string, messageId?: string): void {
  if (!isTTSSupported() || !text) return;

  // 停止之前的播放并递增代际计数器
  // 这会使所有旧 utterance 的 onend / onerror 回调失效
  _generation++;
  window.speechSynthesis.cancel();
  _currentUtterance = null;
  _stopKeepAlive();

  // 先暂停音乐（计数器 +1）
  pauseForTTS();

  // 分句
  _sentences = splitIntoSentences(text);
  if (_sentences.length === 0) {
    resumeAfterTTS();
    return;
  }

  _currentIndex = 0;
  _messageId = messageId || "";
  _setState("playing");

  // 启动保活定时器
  _startKeepAlive();

  // 开始播放第一句（捕获当前代际）
  const gen = _generation;
  _playSentence(0, gen);
}

/**
 * 暂停播放 — 断点续播
 *
 * 调用 speechSynthesis.pause()，可通过 resumePlayback() 恢复。
 */
export function pausePlayback(): void {
  if (!isTTSSupported()) return;
  if (_state !== "playing") return;

  window.speechSynthesis.pause();
  _setState("paused");
}

/**
 * 断点续播 — 从暂停位置恢复播放
 */
export function resumePlayback(): void {
  if (!isTTSSupported()) return;
  if (_state !== "paused") return;

  window.speechSynthesis.resume();
  _setState("playing");
}

/**
 * 单句重放 — 重新播放当前句子
 */
export function replayCurrentSentence(): void {
  if (!isTTSSupported()) return;
  if (_state === "idle" || _sentences.length === 0) return;

  _generation++;
  window.speechSynthesis.cancel();
  _currentUtterance = null;
  _setState("playing");
  _startKeepAlive(); // 确保 Chrome 保活机制运行（防止从 paused 状态重放时缺失保活）
  const gen = _generation;
  _playSentence(_currentIndex, gen);
}

/**
 * 整条重放 — 从第一句重新播放
 */
export function replayPlayback(): void {
  if (!isTTSSupported()) return;
  if (_sentences.length === 0) return;

  _generation++;
  window.speechSynthesis.cancel();
  _currentUtterance = null;
  _currentIndex = 0;
  _setState("playing");
  _startKeepAlive();
  const gen = _generation;
  _playSentence(0, gen);
}

/**
 * 终止播放 — 完全停止，不可续播
 *
 * 用户随时可打断语音播报，优先用户操作。
 */
export function stopPlayback(): void {
  if (!isTTSSupported()) return;

  // 递增代际计数器，使所有待处理的回调失效
  _generation++;
  window.speechSynthesis.cancel();
  _currentUtterance = null;
  _stopKeepAlive();
  _setState("stopped");

  // 立即重置状态（不再使用 setTimeout，避免与新播放竞态）
  _sentences = [];
  _currentIndex = 0;
  _messageId = "";

  // 短暂延迟后回到 idle，让 UI 先渲染 stopped 状态
  // 使用代际检查确保不会干扰后续新播放
  const stopGen = _generation;
  setTimeout(() => {
    // 如果代际已变化（用户在此期间发起新播放），不干预
    if (stopGen !== _generation) return;
    _setState("idle");
  }, 50);

  // 强制恢复音乐（重置计数器）
  resumeAfterTTS();
}

/**
 * 跳转到指定句子播放
 *
 * @param index 句子索引（0-based）
 */
export function jumpToSentence(index: number): void {
  if (!isTTSSupported()) return;
  if (index < 0 || index >= _sentences.length) return;

  _generation++;
  window.speechSynthesis.cancel();
  _currentUtterance = null;
  _setState("playing");
  _startKeepAlive(); // 确保 Chrome 保活机制运行（可能在播放结束后 idle 状态调用）
  const gen = _generation;
  _playSentence(index, gen);
}

// ============================================================
// 向后兼容 API
// ============================================================

/**
 * 朗读文本（兼容旧接口，内部调用分句播放）
 * @deprecated 建议使用 speakSentences() 以获得更好的播放体验
 */
export function speak(text: string): void {
  speakSentences(text);
}

/** 停止朗读（兼容旧接口） */
export function stopSpeaking(): void {
  stopPlayback();
}

/** 是否正在朗读 */
export function isSpeaking(): boolean {
  return _state === "playing" || _state === "paused";
}
