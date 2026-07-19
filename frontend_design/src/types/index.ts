/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

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
  session_id?: string; // 会话 ID
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
  type: string;     // 事件类型: chunk / intent / action / experts / done / error
  data?: {
    chunk?: string;        // 文本块 (type=chunk)
    intent?: string;       // 意图名称 (type=intent)
    source?: string;       // 意图来源 (type=intent)
    action?: string;       // 技能动作 (type=action)
    experts?: string[];    // 专家列表 (type=experts)
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

/** 媒体曲目信息 */
export interface TrackInfo {
  title: string;       // 歌曲标题，如 "爱错 - 王力宏"
  filename: string;    // 文件名，如 "王力宏-爱错.mp3"
  url: string;         // 可直接播放的相对路径，如 "/audio/music/王力宏-爱错.mp3"
  format: string;      // 音频格式，如 "mp3" / "wav"
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
    /** 当前曲目，对象格式，兼容旧版字符串格式 */
    track: string | TrackInfo | null;
    track_index?: number;            // 当前曲目在播放列表中的索引
    playlist?: (string | TrackInfo)[]; // 完整播放列表
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
  index_ready?: boolean; // RediSearch 索引是否就绪
}

// ============================================================
// 扩展类型
// ============================================================

/** 专家状态 */
export interface ExpertStatus {
  name: string;         // 专家名称
  active: boolean;      // 是否活跃
  latency_ms?: number;  // 执行延迟
}

/** 知识库统计 */
export interface KBStats {
  connected: boolean;
  collection?: string;
  total_docs?: number;
  error?: string;
}

// ============================================================
// 座舱管理 / 运营总览 / 中间件 / 设置
// ============================================================

/** 座舱配置 */
export interface Cockpit {
  cockpit_id: string;
  name: string;
  user_id: string;
  vehicle_adapter: string;
  redis_db: number;
  milvus_collection_prefix: string;
  created_at: string;
  is_active: boolean;
  theme_color: string;
}

/** 座舱列表响应 */
export interface CockpitListResponse {
  total: number;
  active: number;
  cockpits: Cockpit[];
}

/** 座舱状态响应 */
export interface CockpitStatus {
  cockpit_id: string;
  name: string;
  is_active: boolean;
  vehicle_status?: Record<string, any>;
  metrics?: Record<string, any>;
}

/** 数据中台全局概览 */
export interface DataPlatformOverview {
  total_chats: number;
  total_vehicle_cmds: number;
  cache_hit_rate: number;
  avg_latency_ms: number;
  cockpit_count: number;
  alert_count_24h: number;
  current_concurrency: number;
  peak_concurrency: number;
}

/** 座舱对比数据 */
export interface CockpitComparison {
  cockpit_id: string;
  name: string;
  chat_count: number;
  vehicle_cmd_count: number;
  cache_hit_rate: number;
  /** 车控成功率（百分比）— 运营对比表中"命中率"列展示 */
  vehicle_cmd_success_rate: number;
  avg_latency_ms: number;
  health_score: number;
}

/** 告警记录 */
export interface AlertRecord {
  id: number;
  cockpit_id: string;
  alert_time: string;
  alert_type: string;
  severity: string;
  subagent_judgment?: string;
  mainagent_judgment?: string;
  action_taken: string;
}

/** Agent 活动记录 */
export interface AgentActivity {
  id: number;
  cockpit_id: string;
  check_time: string;
  is_anomaly: boolean;
  check_items?: string;
  llm_judgment?: string;
}

/** 中间件状态 */
export interface MiddlewareStatus {
  name: string;
  status: string;
  version?: string;
  error?: string;
  [key: string]: any;
}

/** 用户信息 */
export interface User {
  user_id: string;
  username: string;
  cockpit_id: string;
  role: string;
  created_at: string;
}

/** RBAC 角色 */
export type UserRole = "super_admin" | "cockpit_admin" | "cockpit_user" | "cockpit_viewer";

/** 声纹注册状态 */
export interface VoiceprintStatus {
  cockpit_id: string;
  users: {
    user_id: string;
    enroll_count: number;
    completed: boolean;
  }[];
}

/** 声纹验证结果 */
export interface VoiceprintVerifyResult {
  verified: boolean;
  user_id: string | null;
  similarity: number;
  threshold: number;
  message: string;
  // N9: 声纹验证成功后自动签发的 JWT Token
  access_token?: string;
  token_type?: string;
  expires_in?: number;
  auth_method?: string;
}
