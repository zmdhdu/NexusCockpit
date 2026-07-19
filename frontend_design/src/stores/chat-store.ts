/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * 聊天状态管理 — 使用 Zustand 管理全局聊天状态
 *
 * 多会话支持:
 *   - 每个座舱下可以有多个独立会话
 *   - 新建对话：类似豆包/ChatGPT，可创建新对话
 *   - 会话切换：点击侧边栏会话列表切换
 *   - 历史消息加载：从后端加载会话消息记录
 *   - 使用 persist 中间件持久化到 localStorage
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Message } from "@/types";

/** 会话元数据 */
export interface SessionMeta {
  session_id: string;
  title: string;
  message_count: number;
  created_at: string;
  last_message_at: string;
}

/** 聊天状态接口定义 */
interface ChatState {
  /** 当前显示的消息列表 */
  messages: Message[];
  /** 按座舱 ID + 会话 ID 分组存储的对话历史 */
  messagesByKey: Record<string, Message[]>;
  /** 按座舱 ID 分组的会话列表 */
  sessionsByCockpit: Record<string, SessionMeta[]>;
  /** 当前会话 ID */
  sessionId: string;
  /** 是否正在流式接收 */
  isStreaming: boolean;
  /** 当前用户 ID */
  userId: string;
  /** 当前座舱 ID */
  cockpitId: string;

  // 状态操作方法
  setUserId: (id: string) => void;
  /** 切换座舱 ID — 加载该座舱的会话列表 */
  setCockpitId: (id: string) => void;
  /** 设置当前会话 ID */
  setSessionId: (id: string) => void;
  /** 新建会话 */
  newSession: (sessionId: string, title?: string) => void;
  /** 加载会话列表 */
  setSessions: (cockpitId: string, sessions: SessionMeta[]) => void;
  /** 加载会话消息 */
  loadSessionMessages: (sessionId: string, messages: Message[]) => void;
  addMessage: (msg: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  removeMessage: (id: string) => void;
  /** 清空当前会话的消息（新建对话） */
  clearMessages: () => void;
  setStreaming: (streaming: boolean) => void;
  /** 删除会话 */
  removeSession: (sessionId: string) => void;
  /** 更新会话标题（首次消息后用用户问题作为标题） */
  updateSessionTitle: (sessionId: string, title: string) => void;
}

/** 生成存储 key */
function storageKey(cockpitId: string, sessionId: string) {
  return `${cockpitId}:${sessionId}`;
}

// Zustand Store
export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messages: [],
      messagesByKey: {},
      sessionsByCockpit: {},
      sessionId: "",
      isStreaming: false,
      userId: "demo_user",
      cockpitId: "cockpit-01",

      setUserId: (id) => set({ userId: id }),

      setCockpitId: (id) => {
        const state = get();
        // 保存当前会话的消息
        const currentKey = storageKey(state.cockpitId, state.sessionId);
        const updatedByKey = {
          ...state.messagesByKey,
          [currentKey]: state.messages,
        };
        // 加载目标座舱的会话列表
        const targetSessions = state.sessionsByCockpit[id] || [];
        // 如果有会话，加载第一个会话的消息
        const targetSessionId = targetSessions[0]?.session_id || "";
        const targetKey = storageKey(id, targetSessionId);
        const targetMessages = updatedByKey[targetKey] || [];
        set({
          cockpitId: id,
          sessionId: targetSessionId,
          messages: targetMessages,
          messagesByKey: updatedByKey,
        });
      },

      setSessionId: (id) => {
        const state = get();
        // 保存当前会话的消息
        const currentKey = storageKey(state.cockpitId, state.sessionId);
        const updatedByKey = {
          ...state.messagesByKey,
          [currentKey]: state.messages,
        };
        // 加载目标会话的消息
        const targetKey = storageKey(state.cockpitId, id);
        const targetMessages = updatedByKey[targetKey] || [];
        set({
          sessionId: id,
          messages: targetMessages,
          messagesByKey: updatedByKey,
        });
      },

      newSession: (sessionId, title = "新对话") => {
        const state = get();
        // 保存当前会话的消息
        const currentKey = storageKey(state.cockpitId, state.sessionId);
        const updatedByKey = {
          ...state.messagesByKey,
          [currentKey]: state.messages,
        };
        // 添加新会话到列表
        const now = new Date().toISOString();
        const newMeta: SessionMeta = {
          session_id: sessionId,
          title,
          message_count: 0,
          created_at: now,
          last_message_at: now,
        };
        const cockpitSessions = state.sessionsByCockpit[state.cockpitId] || [];
        const updatedSessions = {
          ...state.sessionsByCockpit,
          [state.cockpitId]: [newMeta, ...cockpitSessions],
        };
        set({
          sessionId,
          messages: [],
          messagesByKey: updatedByKey,
          sessionsByCockpit: updatedSessions,
        });
      },

      setSessions: (cockpitId, sessions) => {
        set((state) => ({
          sessionsByCockpit: {
            ...state.sessionsByCockpit,
            [cockpitId]: sessions,
          },
        }));
      },

      loadSessionMessages: (sessionId, messages) => {
        const state = get();
        const key = storageKey(state.cockpitId, sessionId);
        set({
          sessionId,
          messages,
          messagesByKey: {
            ...state.messagesByKey,
            [key]: messages,
          },
        });
      },

      addMessage: (msg) =>
        set((state) => {
          const newMessages = [...state.messages, msg];
          const key = storageKey(state.cockpitId, state.sessionId);
          return {
            messages: newMessages,
            messagesByKey: {
              ...state.messagesByKey,
              [key]: newMessages,
            },
          };
        }),

      updateMessage: (id, updates) =>
        set((state) => {
          const newMessages = state.messages.map((m) =>
            m.id === id ? { ...m, ...updates } : m
          );
          const key = storageKey(state.cockpitId, state.sessionId);
          return {
            messages: newMessages,
            messagesByKey: {
              ...state.messagesByKey,
              [key]: newMessages,
            },
          };
        }),

      removeMessage: (id) =>
        set((state) => {
          const newMessages = state.messages.filter((m) => m.id !== id);
          const key = storageKey(state.cockpitId, state.sessionId);
          return {
            messages: newMessages,
            messagesByKey: {
              ...state.messagesByKey,
              [key]: newMessages,
            },
          };
        }),

      clearMessages: () =>
        set((state) => {
          const key = storageKey(state.cockpitId, state.sessionId);
          return {
            messages: [],
            messagesByKey: {
              ...state.messagesByKey,
              [key]: [],
            },
          };
        }),

      setStreaming: (streaming) => set({ isStreaming: streaming }),

      updateSessionTitle: (sessionId, title) =>
        set((state) => {
          const cockpitSessions = state.sessionsByCockpit[state.cockpitId] || [];
          const updatedSessions = cockpitSessions.map((s) =>
            s.session_id === sessionId ? { ...s, title } : s
          );
          return {
            sessionsByCockpit: {
              ...state.sessionsByCockpit,
              [state.cockpitId]: updatedSessions,
            },
          };
        }),

      removeSession: (sessionId) =>
        set((state) => {
          const cockpitSessions = state.sessionsByCockpit[state.cockpitId] || [];
          const updatedSessions = cockpitSessions.filter((s) => s.session_id !== sessionId);
          // 如果删除的是当前会话，切换到第一个
          if (state.sessionId === sessionId) {
            const nextSessionId = updatedSessions[0]?.session_id || "";
            const nextKey = storageKey(state.cockpitId, nextSessionId);
            const nextMessages = state.messagesByKey[nextKey] || [];
            return {
              sessionId: nextSessionId,
              messages: nextMessages,
              sessionsByCockpit: {
                ...state.sessionsByCockpit,
                [state.cockpitId]: updatedSessions,
              },
            };
          }
          return {
            sessionsByCockpit: {
              ...state.sessionsByCockpit,
              [state.cockpitId]: updatedSessions,
            },
          };
        }),
    }),
    {
      name: "nexus-chat-store-v2",
      partialize: (state) => ({
        messagesByKey: state.messagesByKey,
        sessionsByCockpit: state.sessionsByCockpit,
        sessionId: state.sessionId,
        userId: state.userId,
        cockpitId: state.cockpitId,
      }),
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        // 从 messagesByKey 恢复当前会话的 messages
        const key = `${state.cockpitId}:${state.sessionId}`;
        const currentMessages = state.messagesByKey?.[key] || [];
        state.messages = currentMessages.map((m: any) => ({
          ...m,
          timestamp:
            m.timestamp instanceof Date ? m.timestamp : new Date(m.timestamp),
          loading: false,
        }));
        state.isStreaming = false;
      },
    }
  )
);
