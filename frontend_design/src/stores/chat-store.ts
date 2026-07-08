/**
 * 聊天状态管理 — 使用 Zustand 管理全局聊天状态
 *
 * Zustand 是一个轻量级状态管理库，比 Redux 更简单。
 * 全局状态包括: 消息列表、流式状态、用户 ID。
 *
 * 使用 persist 中间件持久化 messages 和 userId 到 localStorage，
 * 页面刷新后对话不丢失。
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Message } from "@/types";

/** 聊天状态接口定义 */
interface ChatState {
  messages: Message[];    // 消息列表
  isStreaming: boolean;   // 是否正在流式接收
  userId: string;         // 当前用户 ID

  // 状态操作方法
  setUserId: (id: string) => void;                        // 设置用户 ID
  addMessage: (msg: Message) => void;                     // 添加新消息
  updateMessage: (id: string, updates: Partial<Message>) => void;  // 更新消息
  removeMessage: (id: string) => void;                    // 删除消息
  clearMessages: () => void;                               // 清空所有消息
  setStreaming: (streaming: boolean) => void;             // 设置流式状态
}

// 重新导出 Message 类型，方便从 @/stores/chat-store 导入
export type { Message };

// Zustand Store — 全局状态容器
// persist 中间件将 messages 和 userId 持久化到 localStorage
// timestamp (Date 对象) 在持久化时会自动序列化为 ISO 字符串，
// 反序列化时通过 onRehydrateStorage 转回 Date 对象
export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      // 初始状态
      messages: [],
      isStreaming: false,
      userId: "demo_user",

      // 设置用户 ID
      setUserId: (id) => set({ userId: id }),

      // 添加新消息到列表末尾
      addMessage: (msg) =>
        set((state) => ({ messages: [...state.messages, msg] })),

      // 根据 ID 更新指定消息的属性 (如加载完成后更新 content)
      updateMessage: (id, updates) =>
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, ...updates } : m
          ),
        })),

      // 根据 ID 删除消息
      removeMessage: (id) =>
        set((state) => ({
          messages: state.messages.filter((m) => m.id !== id),
        })),

      // 清空所有消息
      clearMessages: () => set({ messages: [] }),

      // 设置流式接收状态 (控制 UI 上的加载动画)
      setStreaming: (streaming) => set({ isStreaming: streaming }),
    }),
    {
      name: "nexus-chat-store",
      // 只持久化 messages 和 userId，不持久化 isStreaming
      partialize: (state) => ({
        messages: state.messages,
        userId: state.userId,
      }),
      // 反序列化时将 timestamp 字符串转回 Date 对象
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        if (state.messages) {
          state.messages = state.messages.map((m) => ({
            ...m,
            timestamp:
              m.timestamp instanceof Date
                ? m.timestamp
                : new Date(m.timestamp),
            // 恢复后重置 loading 状态
            loading: false,
          }));
        }
        // 恢复后重置 streaming 状态
        state.isStreaming = false;
      },
    }
  )
);
