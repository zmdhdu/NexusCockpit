import { ChatWindow } from "@/components/chat/chat-window";

export default function ChatPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">语音助手</h1>
        <p className="text-sm text-muted-foreground">
          与 NexusCockpit AI 对话，支持车控、搜索、点餐等指令
        </p>
      </div>
      <ChatWindow />
    </div>
  );
}
