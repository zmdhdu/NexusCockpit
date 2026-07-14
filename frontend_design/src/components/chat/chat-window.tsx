/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 聊天窗口组件 — 用户与 AI 语音助手交互的核心界面
 *
 * 功能:
 *   - 文本输入 + SSE 流式接收 AI 回复
 *   - 浏览器 Web Speech API 语音识别（实时转写）
 *   - 本地 ASR 录音 → 上传后端 SenseVoice 模型识别
 *   - TTS 语音合成朗读 AI 回复
 *   - 多会话管理（新建/切换/加载历史消息）
 *   - 车控指令联动刷新（检测到车控动作时通知 VehiclePanel 刷新）
 *   - 流式请求可取消（AbortController）
 *   - 降级策略：流式失败时自动回退到非流式请求
 *
 * 数据流:
 *   用户输入 → streamMessage() → 后端 SSE → 逐块更新消息 → TTS 朗读
 */
"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, User, Bot, Square, Mic, MicOff, AudioLines } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useChatStore } from "@/stores/chat-store";
import { useAuth } from "@/stores/auth-store";
import { sendMessage, streamMessage, StreamError, transcribeAudio, createChatSession, listChatSessions, getSessionMessages } from "@/lib/api";
import { emitVehicleRefresh } from "@/lib/vehicle-events";
import { speak } from "@/lib/tts";
import { cn, formatTime } from "@/lib/utils";
import { useSpeechRecognition } from "@/hooks/use-speech-recognition";
import { useAudioRecorder } from "@/hooks/use-audio-recorder";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import type { Message } from "@/types";

export function ChatWindow() {
  const [input, setInput] = useState("");
  const [asrLoading, setAsrLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 流式内容缓存在 ref 中，节流渲染避免阻塞 UI
  const streamingContentRef = useRef("");
  const rafScheduledRef = useRef(false);

  const { messages, addMessage, updateMessage, isStreaming, setStreaming, userId, cockpitId: chatCockpitId, setCockpitId, sessionId, setSessionId, newSession, setSessions, loadSessionMessages, sessionsByCockpit } =
    useChatStore();
  const { cockpitId: authCockpitId } = useAuth();

  // 浏览器 Web Speech API 语音识别
  const {
    isListening,
    transcript,
    error: speechError,
    startListening,
    stopListening,
    resetTranscript,
    supported: speechSupported,
  } = useSpeechRecognition();

  // 本地 ASR 录音 hook
  const {
    isRecording,
    error: recordError,
    startRecording,
    stopRecording,
    supported: recordSupported,
  } = useAudioRecorder();

  // 当 auth store 中的座舱 ID 变化时，同步到 chat store 并加载会话列表
  useEffect(() => {
    if (authCockpitId && authCockpitId !== chatCockpitId) {
      setCockpitId(authCockpitId);
    }
  }, [authCockpitId, chatCockpitId, setCockpitId]);

  // v2.2.2: 加载会话列表（座舱切换时）
  useEffect(() => {
    if (!chatCockpitId) return;
    const sessions = sessionsByCockpit[chatCockpitId];
    if (!sessions || sessions.length === 0) {
      // 从后端加载会话列表
      listChatSessions().then((resp) => {
        if (resp && resp.length > 0) {
          setSessions(chatCockpitId, resp.map(s => ({
            session_id: s.session_id,
            title: s.title,
            message_count: s.message_count,
            created_at: s.created_at,
            last_message_at: s.last_message_at,
          })));
          // 如果没有当前会话，选择第一个
          if (!sessionId && resp[0]) {
            setSessionId(resp[0].session_id);
          }
        } else if (!sessionId) {
          // 没有会话，自动创建一个
          createChatSession("新对话", userId).then((sess) => {
            newSession(sess.session_id, sess.title);
          }).catch(() => {
            // 后端未启动时静默失败
          });
        }
      }).catch(() => {
        // 后端未启动时静默失败
      });
    }
  }, [chatCockpitId]);

  // v2.2.2: 切换会话时从后端加载消息（如果本地缓存为空）
  useEffect(() => {
    if (!sessionId || !chatCockpitId) return;
    const key = `${chatCockpitId}:${sessionId}`;
    const cached = useChatStore.getState().messagesByKey[key];
    if (!cached || cached.length === 0) {
      // 从后端加载会话消息
      getSessionMessages(sessionId).then((msgs) => {
        if (msgs && msgs.length > 0) {
          loadSessionMessages(sessionId, msgs);
        }
      }).catch(() => {
        // 静默失败
      });
    }
  }, [sessionId, chatCockpitId]);

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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 组件卸载时取消正在进行的流式请求
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, []);

  /**
   * 节流刷新流式内容到 UI — 使用 requestAnimationFrame 避免高频 setState 阻塞主线程
   *
   * 流式 SSE 每秒可能产生数十个 chunk，直接 setState 会导致 UI 卡顿。
   * 通过 rAF 合并多个 chunk 为一次渲染，保持 60fps 流畅度。
   */
  const flushStreamingContent = useCallback((assistantId: string) => {
    rafScheduledRef.current = false;
    updateMessage(assistantId, { content: streamingContentRef.current, loading: false });
  }, [updateMessage]);

  const scheduleFlush = useCallback((assistantId: string) => {
    if (!rafScheduledRef.current) {
      rafScheduledRef.current = true;
      requestAnimationFrame(() => flushStreamingContent(assistantId));
    }
  }, [flushStreamingContent]);

  /**
   * 发送消息 — 核心交互逻辑
   *
   * 流程:
   *   1. 将用户消息加入消息列表
   *   2. 创建 AI 回复占位消息（显示"思考中..."）
   *   3. 通过 SSE 流式接收 AI 回复，逐块更新占位消息
   *   4. 收到 done 事件后，触发 TTS 朗读 + 车控面板刷新
   *   5. 若流式失败（404/501），自动降级为非流式请求
   *
   * @param overrideText - 可选的覆盖文本（语音识别结果直接传入，不经过输入框）
   */
  const handleSend = async (overrideText?: string) => {
    const text = (overrideText || input).trim();
    if (!text) return;
    // 如果正在流式处理，先取消旧请求再发新的（不阻塞用户）
    if (isStreaming && abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setStreaming(false);
    }

    setInput("");
    resetTranscript();

    // Add user message
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    addMessage(userMsg);

    // Add placeholder assistant message
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      loading: true,
    };
    addMessage(assistantMsg);
    setStreaming(true);
    streamingContentRef.current = "";

    // 取消上一次未完成的请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      let fullContent = "";
      let intent: string | undefined;
      let action: string | undefined;

      // Try streaming first
      try {
        for await (const event of streamMessage(
          { text, user_id: userId, session_id: sessionId || undefined, stream: true },
          controller.signal
        )) {
          if (event.type === "thinking") {
            updateMessage(assistantId, { content: "", loading: true });
          } else if (event.type === "chunk" && event.data?.chunk) {
            fullContent += event.data.chunk;
            streamingContentRef.current = fullContent;
            // 节流更新 UI，不阻塞其他操作
            scheduleFlush(assistantId);
          } else if (event.type === "intent") {
            intent = event.data?.intent;
          } else if (event.type === "action") {
            action = event.data?.action;
          } else if (event.type === "done") {
            if (event.data?.response) {
              fullContent = event.data.response;
              streamingContentRef.current = fullContent;
            }
            if (event.data?.intent) intent = event.data.intent;
            if (event.data?.action) action = event.data.action;
            updateMessage(assistantId, {
              content: fullContent,
              loading: false,
              intent,
              action,
            });
            // 检查是否涉及车控操作，触发面板刷新
            if (action?.includes("vehicle") || intent?.includes("车") ||
                intent?.includes("空调") || intent?.includes("车窗") ||
                intent?.includes("座椅") || intent?.includes("导航") ||
                intent?.includes("音乐") || intent?.includes("media")) {
              emitVehicleRefresh();
            }
            // TTS 语音合成朗读回复
            speak(fullContent);
          } else if (event.type === "error") {
            const errMsg = event.data?.message || "未知错误";
            toast.error("流式响应错误", { description: errMsg });
            updateMessage(assistantId, {
              content: fullContent || `抱歉，处理请求时出现错误：${errMsg}`,
              loading: false,
            });
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
          try {
            const resp = await sendMessage({ text, user_id: userId, session_id: sessionId || undefined });
            updateMessage(assistantId, {
              content: resp.response,
              loading: false,
              intent: resp.intent,
              action: resp.action,
            });
          } catch (fallbackErr) {
            toast.error("服务不可用", {
              description: "无法连接到后端服务，请检查网络或后端状态。",
            });
            updateMessage(assistantId, {
              content: "抱歉，服务暂时不可用，请稍后重试。",
              loading: false,
            });
          }
        } else {
          const errorMsg =
            streamErr instanceof StreamError && streamErr.status === 401
              ? "鉴权失败，请检查 API Key 配置。"
              : streamErr instanceof StreamError && streamErr.status >= 500
              ? "后端服务异常，请稍后重试。"
              : "网络连接异常，请检查网络后重试。";

          toast.error("请求失败", { description: errorMsg });
          updateMessage(assistantId, {
            content: `抱歉，处理请求时出现错误：${errorMsg}`,
            loading: false,
          });
        }
      }
    } catch (error) {
      updateMessage(assistantId, {
        content: "抱歉，处理请求时出现错误，请稍后重试。",
        loading: false,
      });
    } finally {
      setStreaming(false);
      abortControllerRef.current = null;
    }
  };

  /** 停止正在进行的流式生成 — 调用 AbortController.abort() 中断 fetch 请求 */
  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setStreaming(false);
    }
  };

  /** 键盘事件处理 — Enter 发送，Shift+Enter 换行 */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /** 本地 ASR 录音 → 上传后端识别 → 填入输入框 */
  const handleLocalASRToggle = async () => {
    if (isRecording) {
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
      await startRecording();
    }
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-4">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center space-y-3">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400/20 to-indigo-500/20">
                <Bot className="h-8 w-8 text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">
                开始对话
              </h3>
              <p className="text-sm text-muted-foreground max-w-md">
                你可以对我说："把空调调到24度"、"导航到上海虹桥"、"今天天气怎么样"
              </p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              "flex gap-3 animate-slide-up",
              msg.role === "user" && "flex-row-reverse"
            )}
          >
            {/* Avatar */}
            <div
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-gradient-to-br from-sky-400/20 to-indigo-500/20 text-primary"
              )}
            >
              {msg.role === "user" ? (
                <User className="h-5 w-5" />
              ) : (
                <Bot className="h-5 w-5" />
              )}
            </div>

            {/* Message */}
            <div
              className={cn(
                "flex flex-col gap-1 max-w-[70%]",
                msg.role === "user" && "items-end"
              )}
            >
              <div
                className={cn(
                  "rounded-2xl px-4 py-2.5 text-sm",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground rounded-tr-sm"
                    : "bg-card border border-border rounded-tl-sm"
                )}
              >
                {msg.loading ? (
                  <div className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-muted-foreground">思考中...</span>
                  </div>
                ) : msg.role === "assistant" ? (
                  <div className="prose prose-sm prose-invert max-w-none break-words [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_pre]:my-2 [&_code]:rounded [&_code]:bg-accent [&_code]:px-1 [&_code]:py-0.5">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  msg.content
                )}
              </div>
              <div className="flex items-center gap-2 px-1">
                <span className="text-xs text-muted-foreground">
                  {formatTime(msg.timestamp)}
                </span>
                {msg.intent && (
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
                    {msg.intent}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <Card className="p-3 glass">
        <div className="flex items-center gap-2">
          {/* 浏览器语音识别按钮 */}
          <Button
            size="icon"
            variant={isListening ? "destructive" : "outline"}
            onClick={() => {
              if (isListening) {
                stopListening();
              } else {
                startListening();
              }
            }}
            disabled={!speechSupported}
            title={speechSupported ? (isListening ? "停止录音" : "浏览器语音识别") : "浏览器不支持语音识别"}
            className={cn("shrink-0 transition-all", isListening && "animate-pulse")}
          >
            {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
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
            className={cn("shrink-0 transition-all", isRecording && "animate-pulse")}
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
              isListening ? "正在聆听..." :
              isRecording ? "正在录音..." :
              asrLoading ? "正在识别语音..." :
              "输入消息，或点击麦克风说话..."
            }
            className="flex-1 border-none bg-transparent focus-visible:ring-0"
          />
          {isStreaming ? (
            <Button
              onClick={handleStop}
              size="icon"
              variant="destructive"
              title="停止生成"
            >
              <Square className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              onClick={() => handleSend()}
              disabled={!input.trim()}
              size="icon"
              title="发送"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
        {/* 语音识别错误提示 */}
        {(speechError || recordError) && (
          <div className="mt-1 text-xs text-amber-400">{speechError || recordError}</div>
        )}
        {/* 录音状态提示 */}
        {isRecording && (
          <div className="mt-1 flex items-center gap-2 text-xs text-red-400">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-red-500" />
            正在录音... 再次点击按钮停止并识别
          </div>
        )}
      </Card>
    </div>
  );
}
