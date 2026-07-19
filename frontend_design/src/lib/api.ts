/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

/**
 * API 客户端 — 前端与后端通信的统一入口
 *
 * 使用 axios 创建实例，自动处理:
 *   - JWT Token 认证 (请求拦截器自动添加 Authorization 头)
 *   - 错误统一处理 (响应拦截器打印错误日志)
 *   - 超时控制 (30 秒)
 *
 * 流式请求使用原生 fetch + ReadableStream，支持 AbortSignal 取消。
 */
import axios from "axios";
import type {
  ChatRequest,
  ChatResponse,
  StreamEvent,
  VehicleCommand,
  VehicleStatus,
  HealthData,
  CacheStats,
  Cockpit,
  CockpitListResponse,
  CockpitStatus,
  DataPlatformOverview,
  CockpitComparison,
  AlertRecord,
  AgentActivity,
  MiddlewareStatus,
  User,
  VoiceprintStatus,
  VoiceprintVerifyResult,
  Message,
} from "@/types";

// 后端 API 基础地址，从环境变量读取，默认 Go 网关 (localhost:8080)
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

// 默认开发用户 (开发环境不校验密码，直接签发 Token)
const DEFAULT_USER_ID = "nexus_dev";
const TOKEN_KEY = "nexus_token";

/**
 * 自动获取 JWT Token — 开发环境下自动调用 /auth/token 获取 Token
 * Token 缓存在 localStorage 中，过期后自动重新获取
 * 获取后同步到 auth-store 以供 RBAC 菜单控制使用
 */
async function ensureAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;

  // 检查是否已有 Token
  const existing = localStorage.getItem(TOKEN_KEY);
  if (existing) {
    // 简单检查: 尝试解码 JWT 的 exp 字段
    try {
      const payload = JSON.parse(atob(existing.split(".")[1]));
      const exp = payload.exp * 1000;
      // Token 没过期且包含 role 字段时才复用
      if (Date.now() < exp - 60000 && payload.role) {
        // 同步到 auth-store
        try {
          const { setAuthToken } = await import("@/stores/auth-store");
          setAuthToken(existing);
        } catch {}
        return existing;
      }
    } catch {
      // Token 格式无效，继续重新获取
    }
  }

  // 没有 Token 或已过期，调用 /auth/token 获取新 Token
  try {
    const resp = await fetch(`${API_BASE}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: DEFAULT_USER_ID, password: "" }),
    });
    if (resp.ok) {
      const data = await resp.json();
      const token = data.access_token;
      if (token) {
        localStorage.setItem(TOKEN_KEY, token);
        // 同步到 auth-store 以更新 RBAC 角色
        try {
          const { setAuthToken } = await import("@/stores/auth-store");
          setAuthToken(token);
        } catch {}
        return token;
      }
    }
  } catch {
    // 后端可能未启动，静默失败
  }
  return null;
}

/**
 * 强制刷新 Token — 当 401 错误发生时，清除旧 Token 并重新获取
 */
async function refreshToken(): Promise<string | null> {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    _tokenPromise = ensureAuthToken();
    return _tokenPromise;
  }
  return null;
}

// axios 实例 — 所有 API 请求都通过此实例发送
export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

// 请求拦截器: 自动附加 JWT Token + 座舱 ID
// 使用全局 Promise 确保所有请求等待同一个 Token 获取过程
let _tokenPromise: Promise<string | null> | null = null;

function getTokenPromise(): Promise<string | null> {
  if (!_tokenPromise) {
    _tokenPromise = ensureAuthToken();
  }
  return _tokenPromise;
}

api.interceptors.request.use(async (config) => {
  if (typeof window !== "undefined") {
    const token = await getTokenPromise();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // 附加座舱 ID 请求头，实现多租户隔离
    const cockpitId = localStorage.getItem("nexus_cockpit_id");
    if (cockpitId) {
      config.headers["X-Cockpit-Id"] = cockpitId;
    }
  }
  return config;
});

// 响应拦截器: 统一错误处理 + 401 自动刷新 Token 重试
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // 401 错误且未重试过: 自动刷新 Token 并重试一次
    if (
      error?.response?.status === 401 &&
      !originalRequest._retried &&
      typeof window !== "undefined"
    ) {
      originalRequest._retried = true;
      const newToken = await refreshToken();
      if (newToken) {
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      }
    }

    console.error("[API Error]", error?.response?.status, error?.message);
    return Promise.reject(error);
  }
);

// 重新导出类型，方便从 @/lib/api 统一导入
export type {
  ChatRequest,
  ChatResponse,
  StreamEvent,
  VehicleCommand,
  VehicleStatus,
  HealthData,
  CacheStats,
  Cockpit,
  CockpitListResponse,
  CockpitStatus,
  DataPlatformOverview,
  CockpitComparison,
  AlertRecord,
  AgentActivity,
  MiddlewareStatus,
  User,
  VoiceprintStatus,
  VoiceprintVerifyResult,
};

// ============================================================
// Auth API — 登录/退出
// ============================================================

/** 用户登录 — 调用 /auth/token 获取 JWT Token */
export async function login(userId: string, password: string = ""): Promise<{
  access_token: string;
  token_type: string;
  expires_in: number;
}> {
  const resp = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, password }),
  });
  if (!resp.ok) {
    throw new Error(`登录失败: HTTP ${resp.status}`);
  }
  const data = await resp.json();
  const token = data.access_token;
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    _tokenPromise = Promise.resolve(token);
    // 同步到 auth-store
    try {
      const { setAuthToken } = await import("@/stores/auth-store");
      setAuthToken(token);
    } catch {}
  }
  return data;
}

/** 退出登录 — 清除 Token */
export async function logout(): Promise<void> {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    _tokenPromise = null;
    try {
      const { clearAuth } = await import("@/stores/auth-store");
      clearAuth();
    } catch {}
  }
}

// ============================================================
// Chat API — 对话相关接口
// ============================================================

/** 发送消息 (非流式) — 等待完整回复后返回 */
export async function sendMessage(req: ChatRequest): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>("/chat", req);
  return data;
}

/**
 * 流式发送消息 — 使用 SSE (Server-Sent Events) 逐块接收回复
 * 返回一个异步生成器，每次 yield 一个事件对象
 *
 * @param req 对话请求参数
 * @param signal 可选的 AbortSignal，用于取消正在进行的流式请求
 *   传入后，调用 signal.abort() 会中断 fetch 和 reader.read()
 */
export async function* streamMessage(
  req: ChatRequest,
  signal?: AbortSignal
): AsyncGenerator<StreamEvent> {
  // 获取 JWT Token (与 axios 拦截器共用同一逻辑)
  const token = await getTokenPromise();

  // 使用原生 fetch 发送 POST 请求 (axios 不支持流式读取)
  // 附加座舱 ID 请求头
  const cockpitId = typeof window !== "undefined" ? localStorage.getItem("nexus_cockpit_id") : null;

  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(cockpitId ? { "X-Cockpit-Id": cockpitId } : {}),
    },
    body: JSON.stringify(req),
    signal, // 传入 AbortSignal，支持取消
  });

  if (!response.ok) {
    // 非 2xx 响应，抛出带状态码的错误，由调用方决定回退策略
    throw new StreamError(
      `Stream request failed: ${response.status} ${response.statusText}`,
      response.status
    );
  }

  if (!response.body) return;

  // 使用 ReadableStream 逐块读取响应
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";  // 缓冲区，处理跨 chunk 的不完整行

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // 将新数据追加到缓冲区
      buffer += decoder.decode(value, { stream: true });

      // 按换行符分割，最后一段可能不完整，保留在缓冲区
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;

        const jsonStr = trimmed.slice(6).trim();
        if (jsonStr === "[DONE]") return;
        try {
          const event = JSON.parse(jsonStr);
          yield event;
        } catch {
          // skip invalid JSON
        }
      }
    }

    // 处理缓冲区中剩余的数据
    if (buffer.trim().startsWith("data: ")) {
      const jsonStr = buffer.trim().slice(6).trim();
      if (jsonStr && jsonStr !== "[DONE]") {
        try {
          const event = JSON.parse(jsonStr);
          yield event;
        } catch {
          // skip invalid JSON
        }
      }
    }
  } finally {
    // 无论正常结束还是被 abort，都释放 reader
    reader.releaseLock();
  }
}

/**
 * 流式请求错误 — 携带 HTTP 状态码，便于调用方区分错误类型
 */
export class StreamError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "StreamError";
    this.status = status;
  }
}

// ============================================================
// Vehicle API — 车控相关接口
// ============================================================

/** 发送车控命令 (直接调用，不经过 Agent 工作流) */
export async function sendVehicleCommand(cmd: VehicleCommand) {
  const { data } = await api.post("/vehicle/command", cmd);
  return data;
}

/** 获取车辆当前状态 */
export async function getVehicleStatus(): Promise<VehicleStatus> {
const { data } = await api.get<VehicleStatus>("/vehicle/status");
return data;
}

/** 使用浏览器 GPS 坐标更新当前位置 */
export async function updateVehicleLocation(latitude: number, longitude: number) {
const { data } = await api.post("/vehicle/location", { latitude, longitude });
return data;
}

// ============================================================
// Health & Admin API — 健康检查与管理接口
// ============================================================

/** 健康检查 — 获取后端各组件连接状态 */
export async function getHealth(): Promise<HealthData> {
  const { data } = await api.get<HealthData>("/health");
  return data;
}

/** 获取已注册技能列表 */
export async function getSkills() {
  const { data } = await api.get("/admin/skills");
  return data;
}

/** 修改密码 */
export async function changePassword(oldPassword: string, newPassword: string) {
  const { data } = await api.post("/auth/change-password", {
    old_password: oldPassword,
    new_password: newPassword,
  });
  return data;
}

/** 获取缓存统计信息 */
export async function getCacheStats(): Promise<CacheStats> {
  const { data } = await api.get<CacheStats>("/admin/cache/stats");
  return data;
}

// ============================================================
// v2.0 Admin API — 配置保存 & 知识库管理
// ============================================================

/** 保存系统配置 */
export async function saveConfig(config: Record<string, string>) {
  const { data } = await api.post("/admin/config", config);
  return data;
}

/** 获取知识库统计 */
export async function getKBStats() {
  const { data } = await api.get("/admin/kb/stats");
  return data;
}

/** 上传文档到知识库 */
export async function uploadKBDocument(file: File, category: string = "general") {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("category", category);
  const { data } = await api.post("/admin/kb/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

/** 重建知识库索引 */
export async function reindexKB() {
  const { data } = await api.post("/admin/kb/reindex");
  return data;
}

// ============================================================
// Cockpit API — 座舱管理
// ============================================================

/** 获取所有座舱列表 */
export async function getCockpits(): Promise<CockpitListResponse> {
  const { data } = await api.get<CockpitListResponse>("/settings/cockpits");
  return data;
}

/** 注册新座舱 */
export async function registerCockpit(body: {
  name: string;
  user_id: string;
  vehicle_adapter?: string;
  theme_color?: string;
}): Promise<Cockpit> {
  const { data } = await api.post<Cockpit>("/settings/cockpits", body);
  return data;
}

/** 更新座舱配置 */
export async function updateCockpit(
  cockpitId: string,
  body: Partial<Cockpit>
): Promise<Cockpit> {
  const { data } = await api.put<Cockpit>(`/settings/cockpits/${cockpitId}`, body);
  return data;
}

/** 注销座舱 */
export async function deleteCockpit(cockpitId: string) {
  const { data } = await api.delete(`/settings/cockpits/${cockpitId}`);
  return data;
}

/** 获取座舱状态 */
export async function getCockpitStatus(cockpitId: string): Promise<CockpitStatus> {
  const { data } = await api.get<CockpitStatus>(`/cockpit/${cockpitId}/status`);
  return data;
}

/** 座舱对话（非流式） */
export async function sendCockpitChat(
  cockpitId: string,
  text: string,
  userId: string = "default"
) {
  const { data } = await api.post(`/cockpit/${cockpitId}/chat`, {
    text,
    user_id: userId,
  });
  return data;
}

// ============================================================
// v2.1 DataPlatform API — 数据中台
// ============================================================

/** 数据中台全局概览 */
export async function getDataPlatformOverview(): Promise<DataPlatformOverview> {
  const { data } = await api.get<DataPlatformOverview>("/dataplatform/overview");
  return data;
}

/** 单座舱详情 */
export async function getCockpitDetail(cockpitId: string) {
  const { data } = await api.get(`/dataplatform/cockpit/${cockpitId}`);
  return data;
}

/** 并发能力统计 */
export async function getConcurrency() {
  const { data } = await api.get("/dataplatform/concurrency");
  return data;
}

/** 告警历史 */
export async function getAlerts(hours: number = 24, cockpitId: string = ""): Promise<AlertRecord[]> {
  const params: Record<string, any> = { hours };
  if (cockpitId) params.cockpit_id = cockpitId;
  const { data } = await api.get<AlertRecord[]>("/dataplatform/alerts", { params });
  return data;
}

/** Agent 活动时间线 */
export async function getAgentActivity(hours: number = 24, cockpitId: string = ""): Promise<AgentActivity[]> {
  const params: Record<string, any> = { hours };
  if (cockpitId) params.cockpit_id = cockpitId;
  const { data } = await api.get<AgentActivity[]>("/dataplatform/agent/activity", { params });
  return data;
}

/** 座舱对比数据 */
export async function getCockpitComparison(): Promise<CockpitComparison[]> {
  const { data } = await api.get<CockpitComparison[]>("/dataplatform/comparison");
  return data;
}

// ============================================================
// v2.1 Middleware Status API — 中间件状态
// ============================================================

/** 获取所有中间件状态
 *
 * 兼容两种后端响应格式:
 *   1. Go 网关原生: { total, online, offline, middlewares: { redis: {status:"online"}, ... }, check_time }
 *   2. Python 后端: { redis: {status:"connected", name:"Redis", ...}, milvus: {...}, ... }
 *
 * 统一输出为扁平的 Record<string, MiddlewareStatus>，status 值统一为 "connected"/"disconnected"
 */
export async function getAllMiddlewareStatus(): Promise<Record<string, MiddlewareStatus>> {
  const { data } = await api.get("/middleware/");

  // 格式 1: Go 网关 — 数据嵌套在 middlewares 字段中
  if (data.middlewares && typeof data.middlewares === "object") {
    const result: Record<string, MiddlewareStatus> = {};
    for (const [key, val] of Object.entries(data.middlewares as Record<string, any>)) {
      const rawStatus = val?.status || "unknown";
      // Go 网关用 online/offline，统一映射为 connected/disconnected
      const normalizedStatus =
        rawStatus === "online" ? "connected" :
        rawStatus === "offline" ? "disconnected" :
        rawStatus;
      result[key] = {
        ...val,
        name: val?.name || key,
        status: normalizedStatus,
      };
    }
    return result;
  }

  // 格式 2: Python 后端 — 扁平结构，直接返回
  return data as Record<string, MiddlewareStatus>;
}

/** 获取单个中间件状态 */
export async function getMiddlewareStatus(name: string): Promise<MiddlewareStatus> {
  const { data } = await api.get<MiddlewareStatus>(`/middleware/${name}`);
  return data;
}

// ============================================================
// v2.1 ASR API — 语音转文字
// ============================================================

/** 上传音频文件到后端 ASR 引擎进行语音转文字 */
export async function transcribeAudio(audioBlob: Blob): Promise<{ text: string; success: boolean; message: string }> {
  const formData = new FormData();
  // 根据 blob type 确定文件扩展名
  const ext = audioBlob.type.includes("webm") ? "webm"
    : audioBlob.type.includes("mp4") ? "m4a"
    : audioBlob.type.includes("ogg") ? "ogg"
    : "wav";
  formData.append("file", audioBlob, `recording.${ext}`);
  const { data } = await api.post("/asr/transcribe", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 60000, // ASR 识别可能较慢，设为 60s
  });
  return data;
}

// ============================================================
// v2.1 Settings API — 设置中心
// ============================================================

/** 获取中间件配置 */
export async function getMiddlewareConfig() {
  const { data } = await api.get("/settings/middleware");
  return data;
}

/** 更新中间件配置 */
export async function updateMiddlewareConfig(body: Record<string, any>) {
  const { data } = await api.put("/settings/middleware", body);
  return data;
}

/** 获取用户列表 */
export async function getUsers(): Promise<User[]> {
  const { data } = await api.get<User[]>("/settings/users");
  return data;
}

/** 注册新用户 */
export async function registerUser(body: {
  user_id: string;
  username: string;
  cockpit_id: string;
  role: string;
}): Promise<User> {
  const { data } = await api.post<User>("/settings/users", body);
  return data;
}

// ============================================================
// v2.2.2 Chat Sessions API — 多会话管理
// ============================================================

/** 会话信息 */
export interface ChatSession {
  session_id: string;
  cockpit_id: string;
  user_id: string;
  title: string;
  message_count: number;
  created_at: string;
  last_message_at: string;
}

/** 获取会话列表 */
export async function listChatSessions(): Promise<ChatSession[]> {
  const { data } = await api.get<{ total: number; sessions: ChatSession[] }>("/chat/sessions");
  return data.sessions || [];
}

/** 创建新会话 */
export async function createChatSession(title: string = "新对话", userId: string = "default"): Promise<ChatSession> {
  const { data } = await api.post<ChatSession>("/chat/sessions", { title, user_id: userId });
  return data;
}

/** 删除会话 */
export async function deleteChatSession(sessionId: string) {
  const { data } = await api.delete(`/chat/sessions/${sessionId}`);
  return data;
}

/** 获取会话消息记录 */
export async function getSessionMessages(sessionId: string): Promise<Message[]> {
  const { data } = await api.get<{ messages: any[] }>(`/chat/sessions/${sessionId}/messages`);
  return (data.messages || []).map((m: any) => ({
    id: crypto.randomUUID(),
    role: m.role,
    content: m.content,
    timestamp: new Date(m.timestamp),
    intent: m.intent,
    action: m.action,
    loading: false,
  }));
}

// ============================================================
// v2.1 Voiceprint API — 声纹注册/验证
// ============================================================

/** 获取声纹注册状态 */
export async function getVoiceprintStatus(cockpitId: string = ""): Promise<VoiceprintStatus | any> {
  const params: Record<string, any> = {};
  if (cockpitId) params.cockpit_id = cockpitId;
  const { data } = await api.get("/settings/voiceprint/status", { params });
  return data;
}

/** 声纹注册 */
export async function enrollVoiceprint(
  cockpitId: string,
  userId: string,
  audioFile: File
) {
  const formData = new FormData();
  formData.append("cockpit_id", cockpitId);
  formData.append("user_id", userId);
  formData.append("audio", audioFile);
  const { data } = await api.post("/settings/voiceprint/enroll", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

/** 声纹验证 — 验证成功后自动保存 JWT Token（N9） */
export async function verifyVoiceprint(
  cockpitId: string,
  audioFile: File
): Promise<VoiceprintVerifyResult> {
  const formData = new FormData();
  formData.append("cockpit_id", cockpitId);
  formData.append("audio", audioFile);
  const { data } = await api.post<VoiceprintVerifyResult>(
    "/settings/voiceprint/verify",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } }
  );

  // N9: 声纹验证成功后保存 JWT Token，自动登录
  if (data.verified && data.access_token) {
    localStorage.setItem(TOKEN_KEY, data.access_token);
    _tokenPromise = Promise.resolve(data.access_token);
    // 同步到 auth-store 以更新 RBAC 角色
    try {
      const { setAuthToken } = await import("@/stores/auth-store");
      setAuthToken(data.access_token);
    } catch {}
  }

  return data;
}

/** 删除声纹 */
export async function deleteVoiceprint(userId: string, cockpitId: string = "") {
  const params: Record<string, any> = {};
  if (cockpitId) params.cockpit_id = cockpitId;
  const { data } = await api.delete(`/settings/voiceprint/${userId}`, { params });
  return data;
}
