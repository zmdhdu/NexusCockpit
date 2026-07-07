"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, User, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useChatStore, type Message } from "@/stores/chat-store";
import { sendMessage, streamMessage } from "@/lib/api";
import { cn, formatTime } from "@/lib/utils";

export function ChatWindow() {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { messages, addMessage, updateMessage, isStreaming, setStreaming, userId } =
    useChatStore();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

    try {
      let fullContent = "";
      let intent: string | undefined;
      let action: string | undefined;

      // Try streaming first
      try {
        for await (const event of streamMessage({ text, user_id: userId, stream: true })) {
          if (event.type === "chunk" && event.data?.chunk) {
            fullContent += event.data.chunk;
            updateMessage(assistantId, { content: fullContent, loading: false });
          } else if (event.type === "intent") {
            intent = event.data?.intent;
          } else if (event.type === "action") {
            action = event.data?.action;
          } else if (event.type === "done") {
            if (event.data?.response) {
              fullContent = event.data.response;
            }
            updateMessage(assistantId, {
              content: fullContent,
              loading: false,
              intent,
              action,
            });
          }
        }
      } catch {
        // Fallback to non-streaming
        const resp = await sendMessage({ text, user_id: userId });
        updateMessage(assistantId, {
          content: resp.response,
          loading: false,
          intent: resp.intent,
          action: resp.action,
        });
      }
    } catch (error) {
      updateMessage(assistantId, {
        content: "抱歉，处理请求时出现错误，请稍后重试。",
        loading: false,
      });
    } finally {
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
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            size="icon"
          >
            {isStreaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </Card>
    </div>
  );
}
