/**
 * 聊天状态管理 — 使用 Zustand 管理全局聊天状态
 *
 * Zustand 是一个轻量级状态管理库，比 Redux 更简单。
 * 全局状态包括: 消息列表、流式状态、用户 ID。
 */
import { create } from "zustand";

/** 单条消息的数据结构 */
export interface Message {
  id: string;                              // 消息唯一 ID
  role: "user" | "assistant" | "system";  // 角色: 用户/助手/系统
  content: string;                          // 消息文本
  timestamp: Date;                          // 时间戳
  intent?: string;                          // 识别到的意图 (仅助手消息)
  action?: string;                          // 执行的技能 (仅助手消息)
  loading?: boolean;                        // 是否正在加载中 (显示转圈动画)
}

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

// Zustand Store — 全局状态容器
// create() 创建一个可在任何组件中使用的 store
export const useChatStore = create<ChatState>((set) => ({
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
}));
