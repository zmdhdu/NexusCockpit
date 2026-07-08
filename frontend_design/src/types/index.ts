/**
 * 统一类型定义 — 全局共享的 TypeScript 接口与类型
 *
 * 所有跨模块复用的类型都集中在此文件导出，
 * 避免在 api.ts / chat-store.ts / page.tsx 中重复定义。
 */

// ============================================================
// Chat 相关类型
// ============================================================

/** 对话请求参数 */
export interface ChatRequest {
  text: string;       // 用户输入文本
  user_id: string;    // 用户 ID
  stream?: boolean;   // 是否流式返回
}

/** 对话响应数据 */
export interface ChatResponse {
  response: string;       // 回复文本
  user_id?: string;       // 用户 ID
  session_id?: string;    // 会话 ID
  latency_ms?: number;    // 总延迟 (毫秒)
  metadata?: Record<string, any>;  // 元数据
  cache_hit?: boolean;    // 是否命中缓存
  intent?: string;        // 识别到的意图
  action?: string;        // 执行的技能动作
  trace_id?: string;      // 追踪 ID (用于 Langfuse)
}

/** 流式事件类型 */
export interface StreamEvent {
  type: string;     // 事件类型: chunk / intent / action / done / error
  data?: {
    chunk?: string;        // 文本块 (type=chunk)
    intent?: string;       // 意图名称 (type=intent)
    action?: string;       // 技能动作 (type=action)
    response?: string;     // 完整回复 (type=done)
    latency_ms?: number;   // 延迟 (type=done)
    message?: string;      // 错误信息 (type=error)
  };
}

/** 单条消息的数据结构 */
export interface Message {
  id: string;                              // 消息唯一 ID
  role: "user" | "assistant" | "system";   // 角色: 用户/助手/系统
  content: string;                          // 消息文本
  timestamp: Date;                          // 时间戳
  intent?: string;                          // 识别到的意图 (仅助手消息)
  action?: string;                          // 执行的技能 (仅助手消息)
  loading?: boolean;                        // 是否正在加载中 (显示转圈动画)
}

// ============================================================
// Vehicle 相关类型
// ============================================================

/** 车控命令请求 */
export interface VehicleCommand {
  command: string;                    // 命令名称 (如 vehicle_climate)
  arguments: Record<string, any>;     // 命令参数
}

/** 车辆完整状态 */
export interface VehicleStatus {
  climate: {        // 空调状态
    temperature: number;
    fan_speed: number;
    mode: string;
    power: boolean;
  };
  windows: Record<string, number>;   // 各车窗开度百分比
  seats: Record<string, any>;        // 座椅状态
  media: {          // 媒体播放状态
    playing: boolean;
    volume: number;
    source: string;
    track: string;
  };
  navigation: {     // 导航状态
    destination: string;
    mode: string;
  };
  status: {         // 车辆整体状态
    tire_pressure: string;
    range_km: number;
    fuel_percent: number;
    battery_percent: number;
    maintenance: string;
  };
}

// ============================================================
// Health & Admin 相关类型
// ============================================================

/** 健康检查数据 */
export interface HealthData {
  status: string;                       // 整体状态: healthy / offline
  services: Record<string, string>;     // 各服务状态
}

/** 缓存统计数据 */
export interface CacheStats {
  hits: number;        // 命中次数
  misses: number;      // 未命中次数
  hit_rate: number;    // 命中率 (%)
  size: number;        // 缓存大小
}
