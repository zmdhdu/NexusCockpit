/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { useState, useEffect, useRef, useCallback } from "react";

/**
 * 语音识别 Hook — 使用 Web Speech API 进行语音转文字
 *
 * 支持:
 *   - 开始/停止语音识别
 *   - 实时返回识别结果
 *   - 自动处理浏览器兼容性
 */
export function useSpeechRecognition() {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<any>(null);
  const supportedRef = useRef(false);

  useEffect(() => {
    // 浏览器兼容性检查
    const SpeechRecognition =
      (typeof window !== "undefined" && (window as any).SpeechRecognition) ||
      (typeof window !== "undefined" && (window as any).webkitSpeechRecognition);

    if (!SpeechRecognition) {
      setError("当前浏览器不支持语音识别，请使用 Chrome 浏览器");
      supportedRef.current = false;
      return;
    }

    supportedRef.current = true;

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "zh-CN";

    recognition.onresult = (event: any) => {
      let finalTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        finalTranscript += event.results[i][0].transcript;
      }
      setTranscript(finalTranscript);
    };

    recognition.onerror = (event: any) => {
      // 不在 "no-speech" 和 "aborted" 时显示错误（这些是正常行为）
      if (event.error && event.error !== "no-speech" && event.error !== "aborted") {
        setError(`语音识别错误: ${event.error}`);
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;

    return () => {
      try {
        recognition.stop();
      } catch {
        // ignore
      }
    };
  }, []);

  const startListening = useCallback(() => {
    if (!recognitionRef.current) return;
    setTranscript("");
    setError(null);
    try {
      recognitionRef.current.start();
      setIsListening(true);
    } catch {
      // 可能是重复 start
    }
  }, []);

  const stopListening = useCallback(() => {
    if (!recognitionRef.current) return;
    try {
      recognitionRef.current.stop();
    } catch {
      // ignore
    }
    setIsListening(false);
  }, []);

  const resetTranscript = useCallback(() => {
    setTranscript("");
    setError(null);
  }, []);

  return {
    isListening,
    transcript,
    error,
    startListening,
    stopListening,
    resetTranscript,
    supported: supportedRef.current,
  };
}
