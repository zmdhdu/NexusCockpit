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
} from "@/types";

// 后端 API 基础地址，从环境变量读取，默认 localhost:8000
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// 默认开发用户 (开发环境不校验密码，直接签发 Token)
const DEFAULT_USER_ID = "nexus_dev";
const TOKEN_KEY = "nexus_token";

/**
 * 自动获取 JWT Token — 开发环境下自动调用 /auth/token 获取 Token
 * Token 缓存在 localStorage 中，过期后自动重新获取
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
      if (Date.now() < exp - 60000) {
        // 还没过期 (留 1 分钟缓冲)
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

// 请求拦截器: 自动附加 JWT Token (如果用户已登录)
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
};

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
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
