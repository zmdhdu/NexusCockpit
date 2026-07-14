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
 */

let _isSpeaking = false;

/** 是否支持语音合成 */
export function isTTSSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** 朗读文本（如果正在朗读会先停止） */
export function speak(text: string): void {
  if (!isTTSSupported() || !text) return;

  // 停止之前的朗读
  window.speechSynthesis.cancel();

  // 清理 markdown 标记
  const cleanText = text
    .replace(/```[\s\S]*?```/g, "代码块")
    .replace(/[*_#`~]/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .trim();

  if (!cleanText) return;

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
  };
  utterance.onerror = () => {
    _isSpeaking = false;
  };

  window.speechSynthesis.speak(utterance);
}

/** 停止朗读 */
export function stopSpeaking(): void {
  if (isTTSSupported()) {
    window.speechSynthesis.cancel();
    _isSpeaking = false;
  }
}

/** 是否正在朗读 */
export function isSpeaking(): boolean {
  return _isSpeaking;
}
