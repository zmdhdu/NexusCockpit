"use client";

import { useState, useRef, useEffect } from "react";
import {
  Mic,
  MicOff,
  Send,
  Loader2,
  Square,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useChatStore } from "@/stores/chat-store";
import { streamMessage, StreamError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useSpeechRecognition } from "@/hooks/use-speech-recognition";
import type { Message } from "@/types";

/**
 * 语音助手栏 — 集成在车控面板顶部的快捷语音/文字输入区
 *
 * 功能:
 *   - 麦克风按钮：点击开始语音识别，再次点击停止
 *   - 文字输入：支持回车发送
 *   - 快捷指令：一键发送常用车控命令
 *   - 流式回复：与聊天页面相同的 SSE 流式体验
 *   - 回复展示：助手回复以气泡形式显示在输入区上方
 */
export function VoiceAssistantBar() {
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [assistantReply, setAssistantReply] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const { userId } = useChatStore();

  const {
    isListening,
    transcript,
    error: speechError,
    startListening,
    stopListening,
    resetTranscript,
    supported,
  } = useSpeechRecognition();

  // 语音识别结果实时同步到输入框
  useEffect(() => {
    if (transcript) {
      setInput(transcript);
    }
  }, [transcript]);

  // 语音识别停止后自动发送
  useEffect(() => {
    if (!isListening && transcript) {
      // 延迟一点确保最终结果已更新
      const timer = setTimeout(() => {
        if (input.trim()) {
          handleSend();
        }
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [isListening]);

  // 组件卸载时取消请求
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleSend = async (text?: string) => {
    const message = (text || input).trim();
    if (!message || isStreaming) return;

    setInput("");
    resetTranscript();
    setReplyLoading(true);
    setAssistantReply("");
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
            setAssistantReply(fullContent);
            setReplyLoading(false);
          } else if (event.type === "done") {
            if (event.data?.response) {
              setAssistantReply(event.data.response);
            }
            setReplyLoading(false);
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
          // 回退提示
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
        {/* 麦克风按钮 */}
        <Button
          size="icon"
          variant={isListening ? "destructive" : "default"}
          onClick={handleMicToggle}
          disabled={!supported || isStreaming}
          title={supported ? "点击说话" : "浏览器不支持语音识别"}
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

        {/* 文字输入 */}
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isListening ? "正在聆听..." : "语音或文字输入指令..."
          }
          disabled={isStreaming}
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
            disabled={isStreaming}
            className="rounded-full bg-accent/50 px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            {cmd.label}
          </button>
        ))}
      </div>

      {/* 语音识别错误提示 */}
      {speechError && (
        <div className="text-xs text-amber-400">{speechError}</div>
      )}
    </Card>
  );
}
