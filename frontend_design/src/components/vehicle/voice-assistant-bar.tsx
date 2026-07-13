/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  Mic,
  MicOff,
  Send,
  Loader2,
  Square,
  Sparkles,
  AudioLines,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useChatStore } from "@/stores/chat-store";
import { useAuth } from "@/stores/auth-store";
import { streamMessage, StreamError, transcribeAudio } from "@/lib/api";
import { emitVehicleRefresh } from "@/lib/vehicle-events";
import { speak } from "@/lib/tts";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useSpeechRecognition } from "@/hooks/use-speech-recognition";
import { useAudioRecorder } from "@/hooks/use-audio-recorder";

/**
 * 语音助手栏 — 集成在车控面板顶部的快捷语音/文字输入区
 *
 * 功能:
 *   - 麦克风按钮（浏览器语音识别）：点击开始语音识别，再次点击停止
 *   - 本地 ASR 按钮（录音上传后端识别）：使用本地 SenseVoice 模型转文字
 *   - 文字输入：支持回车发送
 *   - 快捷指令：一键发送常用车控命令
 *   - 流式回复：与聊天页面相同的 SSE 流式体验
 *   - 回复展示：助手回复以气泡形式显示在输入区上方
 *
 * 并发优化:
 *   - 流式内容使用 useRef 缓存，通过 requestAnimationFrame 节流渲染
 *   - 流式过程中不阻塞车控面板其他按钮操作
 *   - 新请求可中断旧请求，无需等待
 */
export function VoiceAssistantBar() {
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [assistantReply, setAssistantReply] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const [asrLoading, setAsrLoading] = useState(false);

  // 流式内容缓存在 ref 中，避免每个 chunk 都触发重渲染
  const streamingContentRef = useRef("");
  // rAF 节流标记，防止过多重渲染
  const rafScheduledRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const { userId, cockpitId: chatCockpitId, setCockpitId } = useChatStore();
  const { cockpitId: authCockpitId } = useAuth();

  // 浏览器 Web Speech API 语音识别
  const {
    isListening,
    transcript,
    error: speechError,
    startListening,
    stopListening,
    resetTranscript,
    supported,
  } = useSpeechRecognition();

  // 本地 ASR 录音 hook
  const {
    isRecording,
    error: recordError,
    startRecording,
    stopRecording,
    supported: recordSupported,
  } = useAudioRecorder();

  // 当 auth store 中的座舱 ID 变化时，同步到 chat store
  useEffect(() => {
    if (authCockpitId && authCockpitId !== chatCockpitId) {
      setCockpitId(authCockpitId);
    }
  }, [authCockpitId, chatCockpitId, setCockpitId]);

  // 语音识别结果实时同步到输入框
  useEffect(() => {
    if (transcript) {
      setInput(transcript);
    }
  }, [transcript]);

  // 语音识别停止后自动发送
  useEffect(() => {
    if (!isListening && transcript) {
      const timer = setTimeout(() => {
        if (transcript.trim()) {
          handleSend(transcript.trim());
        }
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [isListening, transcript]);

  // 组件卸载时取消请求
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  /** 节流更新 assistantReply 状态，使用 rAF 避免高频重渲染阻塞 UI */
  const flushStreamingContent = useCallback(() => {
    rafScheduledRef.current = false;
    setAssistantReply(streamingContentRef.current);
  }, []);

  const scheduleFlush = useCallback(() => {
    if (!rafScheduledRef.current) {
      rafScheduledRef.current = true;
      requestAnimationFrame(flushStreamingContent);
    }
  }, [flushStreamingContent]);

  const handleSend = async (text?: string) => {
    const message = (text || input).trim();
    if (!message) return;
    // 如果正在流式处理，先取消旧请求再发新的（不阻塞用户）
    if (isStreaming && abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
    }

    setInput("");
    resetTranscript();
    setReplyLoading(true);
    setAssistantReply("");
    streamingContentRef.current = "";
    setIsStreaming(true);

    // 取消上一次请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      let fullContent = "";

      try {
        for await (const event of streamMessage(
          { text: message, user_id: userId, stream: true },
          controller.signal
        )) {
          if (event.type === "chunk" && event.data?.chunk) {
            fullContent += event.data.chunk;
            streamingContentRef.current = fullContent;
            // 节流更新 UI，不阻塞其他组件
            scheduleFlush();
            setReplyLoading(false);
          } else if (event.type === "done") {
            if (event.data?.response) {
              fullContent = event.data.response;
              streamingContentRef.current = fullContent;
            }
            setAssistantReply(fullContent);
            setReplyLoading(false);
            // TTS 语音合成朗读回复
            if (event.data?.response) {
              speak(event.data.response);
            }
            // 检查是否涉及车控操作，触发面板刷新
            const action = event.data?.action || "";
            const intent = event.data?.intent || "";
            if (action.includes("vehicle") || intent.includes("车") ||
                intent.includes("空调") || intent.includes("车窗") ||
                intent.includes("座椅") || intent.includes("导航") ||
                intent.includes("音乐") || intent.includes("media")) {
              emitVehicleRefresh();
            }
          } else if (event.type === "error") {
            const errMsg = event.data?.message || "未知错误";
            setAssistantReply(`抱歉，处理请求时出现错误：${errMsg}`);
            setReplyLoading(false);
          }
        }
      } catch (streamErr) {
        if (streamErr instanceof DOMException && streamErr.name === "AbortError") {
          return;
        }

        const shouldFallback =
          streamErr instanceof StreamError &&
          (streamErr.status === 404 || streamErr.status === 501);

        if (shouldFallback) {
          setAssistantReply("当前服务暂不可用，请稍后重试。");
        } else {
          const errorMsg =
            streamErr instanceof StreamError && streamErr.status === 401
              ? "鉴权失败，请检查 API Key 配置。"
              : streamErr instanceof StreamError && streamErr.status >= 500
              ? "后端服务异常，请稍后重试。"
              : "网络连接异常，请检查网络后重试。";
          setAssistantReply(`抱歉，处理请求时出现错误：${errorMsg}`);
        }
        setReplyLoading(false);
      }
    } catch {
      setAssistantReply("抱歉，处理请求时出现错误，请稍后重试。");
      setReplyLoading(false);
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
      // 最终刷新一次确保内容完整
      if (streamingContentRef.current) {
        setAssistantReply(streamingContentRef.current);
      }
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleMicToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  /** 本地 ASR 录音 → 上传后端识别 → 填入输入框 */
  const handleLocalASRToggle = async () => {
    if (isRecording) {
      // 停止录音并获取音频 Blob
      const blob = await stopRecording();
      if (!blob) return;

      setAsrLoading(true);
      try {
        const result = await transcribeAudio(blob);
        if (result.success && result.text) {
          setInput(result.text);
          toast.success("语音识别成功", { description: result.text.slice(0, 50) });
        } else {
          toast.warning("未识别到语音内容", {
            description: result.message || "请重试",
          });
        }
      } catch (err: any) {
        toast.error("语音识别失败", {
          description: err?.message || "请检查 ASR 服务是否正常",
        });
      } finally {
        setAsrLoading(false);
      }
    } else {
      // 开始录音
      await startRecording();
    }
  };

  // 快捷指令
  const quickCommands = [
    { label: "空调24度", text: "把空调调到24度" },
    { label: "打开车窗", text: "打开所有车窗" },
    { label: "播放音乐", text: "播放音乐" },
    { label: "主驾加热", text: "打开主驾座椅加热" },
  ];

  return (
    <Card className="glass p-4 space-y-3">
      {/* 助手回复区域 */}
      {(assistantReply || replyLoading) && (
        <div className="flex gap-3 animate-slide-up">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-sky-400/20 to-indigo-500/20">
            <Sparkles className="h-4 w-4 text-primary" />
          </div>
          <div className="flex-1 rounded-2xl bg-card border border-border px-4 py-2.5 text-sm">
            {replyLoading ? (
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-muted-foreground">正在处理...</span>
              </div>
            ) : (
              assistantReply
            )}
          </div>
        </div>
      )}

      {/* 语音/文字输入区 */}
      <div className="flex items-center gap-2">
        {/* 浏览器语音识别按钮 */}
        <Button
          size="icon"
          variant={isListening ? "destructive" : "default"}
          onClick={handleMicToggle}
          disabled={!supported}
          title={supported ? "浏览器语音识别" : "浏览器不支持语音识别"}
          className={cn(
            "shrink-0 transition-all",
            isListening && "animate-pulse"
          )}
        >
          {isListening ? (
            <MicOff className="h-4 w-4" />
          ) : (
            <Mic className="h-4 w-4" />
          )}
        </Button>

        {/* 本地 ASR 录音按钮 — 使用后端 SenseVoice 模型 */}
        <Button
          size="icon"
          variant={isRecording ? "destructive" : "outline"}
          onClick={handleLocalASRToggle}
          disabled={!recordSupported || asrLoading}
          title={
            !recordSupported
              ? "浏览器不支持录音"
              : isRecording
              ? "停止录音并识别"
              : "本地 ASR 语音识别"
          }
          className={cn(
            "shrink-0 transition-all",
            isRecording && "animate-pulse"
          )}
        >
          {asrLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <AudioLines className="h-4 w-4" />
          )}
        </Button>

        {/* 文字输入 */}
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isListening
              ? "正在聆听..."
              : isRecording
              ? "正在录音..."
              : asrLoading
              ? "正在识别语音..."
              : "语音或文字输入指令..."
          }
          className="flex-1"
        />

        {/* 发送/停止按钮 */}
        {isStreaming ? (
          <Button
            onClick={handleStop}
            size="icon"
            variant="destructive"
            title="停止生成"
            className="shrink-0"
          >
            <Square className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            onClick={() => handleSend()}
            disabled={!input.trim()}
            size="icon"
            title="发送"
            className="shrink-0"
          >
            <Send className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* 快捷指令 */}
      <div className="flex flex-wrap gap-2">
        {quickCommands.map((cmd) => (
          <button
            key={cmd.label}
            onClick={() => handleSend(cmd.text)}
            disabled={false}
            className="rounded-full bg-accent/50 px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            {cmd.label}
          </button>
        ))}
      </div>

      {/* 语音识别错误提示 */}
      {(speechError || recordError) && (
        <div className="text-xs text-amber-400">{speechError || recordError}</div>
      )}

      {/* 录音状态提示 */}
      {isRecording && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-red-500" />
          正在录音... 再次点击按钮停止并识别
        </div>
      )}
    </Card>
  );
}
