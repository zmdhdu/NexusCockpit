/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * TTS 语音合成工具 — 使用浏览器内置 Web Speech API
 *
 * 当语音助手完成回复后，自动朗读回复内容，提醒用户操作已完成。
 * 无需服务端模型，零延迟、零依赖。
 *
 * 音乐联动:
 *   朗读开始前自动暂停座舱音乐（保留播放进度），
 *   朗读结束后从断点恢复播放。
 *   用户在朗读期间手动暂停音乐则不会自动恢复。
 */

import { pauseForTTS, resumeAfterTTS } from "@/stores/audio-store";

let _isSpeaking = false;

/** 是否支持语音合成 */
export function isTTSSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** 朗读文本（如果正在朗读会先停止） */
export function speak(text: string): void {
  if (!isTTSSupported() || !text) return;

  // 先暂停音乐（计数器 +1），即使后续 cancel() 触发上一句 onend → resumeAfterTTS，
  // 计数器仍 > 0，不会提前恢复
  pauseForTTS();

  // 停止之前的朗读（会触发上一句的 onend → resumeAfterTTS，计数器 -1）
  window.speechSynthesis.cancel();

  // 清理 markdown 标记
  const cleanText = text
    .replace(/```[\s\S]*?```/g, "代码块")
    .replace(/[*_#`~]/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .trim();

  if (!cleanText) {
    // 没有可朗读的内容，恢复音乐
    resumeAfterTTS();
    return;
  }

  const utterance = new SpeechSynthesisUtterance(cleanText);
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

  utterance.onstart = () => {
    _isSpeaking = true;
  };
  utterance.onend = () => {
    _isSpeaking = false;
    // 朗读结束，恢复音乐（计数器 -1，归零则断点续播）
    resumeAfterTTS();
  };
  utterance.onerror = () => {
    _isSpeaking = false;
    // 出错也要恢复音乐
    resumeAfterTTS();
  };

  window.speechSynthesis.speak(utterance);
}

/** 停止朗读 */
export function stopSpeaking(): void {
  if (isTTSSupported()) {
    window.speechSynthesis.cancel();
    _isSpeaking = false;
  }
  // 强制恢复音乐（重置计数器）
  // cancel() 会触发 onend → resumeAfterTTS，但这里额外确保恢复
  resumeAfterTTS();
}

/** 是否正在朗读 */
export function isSpeaking(): boolean {
  return _isSpeaking;
}
