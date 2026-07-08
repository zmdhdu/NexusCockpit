"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, User, Bot, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useChatStore } from "@/stores/chat-store";
import { sendMessage, streamMessage, StreamError } from "@/lib/api";
import { cn, formatTime } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import type { Message } from "@/types";

export function ChatWindow() {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const { messages, addMessage, updateMessage, isStreaming, setStreaming, userId } =
    useChatStore();

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

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    setInput("");

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
          { text, user_id: userId, stream: true },
          controller.signal
        )) {
          if (event.type === "chunk" && event.data?.chunk) {
            fullContent += event.data.chunk;
            updateMessage(assistantId, { content: fullContent, loading: false });
          } else if (event.type === "intent") {
            intent = event.data?.intent;
          } else if (event.type === "action") {
            action = event.data?.action;
          } else if (event.type === "done") {
            // 使用 done 事件中的完整回复（如有）覆盖累积内容
            if (event.data?.response) {
              fullContent = event.data.response;
            }
            // 如果 done 事件携带了 intent/action，优先使用
            if (event.data?.intent) intent = event.data.intent;
            if (event.data?.action) action = event.data.action;
            updateMessage(assistantId, {
              content: fullContent,
              loading: false,
              intent,
              action,
            });
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
        // 如果是被 abort 取消的，不做任何回退
        if (streamErr instanceof DOMException && streamErr.name === "AbortError") {
          return;
        }

        // 区分错误类型：
        // - 404 / 不支持流式 → 回退到非流式
        // - 其他错误（网络断开、401、500）→ 直接报错，不回退
        const shouldFallback =
          streamErr instanceof StreamError &&
          (streamErr.status === 404 || streamErr.status === 501);

        if (shouldFallback) {
          // 回退到非流式请求
          try {
            const resp = await sendMessage({ text, user_id: userId });
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
          // 网络错误、鉴权失败等 — 不回退，直接报错
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

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
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
                  /* 使用 react-markdown 渲染助手回复，支持 GFM 语法 */
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
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息，或说出你的指令..."
            disabled={isStreaming}
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
              onClick={handleSend}
              disabled={!input.trim()}
              size="icon"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
