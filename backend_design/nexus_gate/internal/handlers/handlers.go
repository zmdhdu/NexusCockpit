// Copyright (c) 2026 zhangmengdi (NexusCockpit)
// Licensed under the MIT License. See LICENSE in the project root for details.
// Source: https://github.com/zmdhdu/NexusCockpit

// Package handlers — Go 原生处理非 AI 请求（W1/N2）
//
// 设计思想: Go 网关直接处理不需要 AI 的请求，减少 Python 服务负载。
// 仅 AI 相关请求（chat/vehicle/asr/tts）才转发给 Python。
//
// 原生处理的路由:
//   GET  /health                    → 增强版健康检查（含中间件状态）
//   GET  /middleware/               → 检查所有中间件连通性
//   GET  /middleware/:name          → 检查单个中间件状态
//   GET  /dataplatform/overview     → 从 Redis 获取基本统计
//   GET  /dataplatform/concurrency  → 返回并发指标
//   GET  /dataplatform/alerts       → 返回告警历史（Demo: 查 Redis）
//   GET  /settings/cockpits         → 返回座舱列表
package handlers

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"nexus_gate/internal/config"
)

// MiddlewareStatus 中间件状态结构体。
// 用于描述单个中间件（Redis/MySQL/Milvus 等）的连通性检查结果。
//
// 字段说明:
//   - Name:    中间件名称（如 "redis"、"mysql"）
//   - Status:  连通状态，"online" 或 "offline"
//   - Latency: TCP 连接延迟（毫秒）
//   - Error:   连接失败时的错误信息（仅 offline 时存在）
//   - Extra:   附加信息（如版本号、连接池大小等，可选）
type MiddlewareStatus struct {
	Name    string `json:"name"`
	Status  string `json:"status"`
	Latency int64  `json:"latency_ms"`
	Error   string `json:"error,omitempty"`
	Extra   map[string]interface{} `json:"extra,omitempty"`
}

// CockpitInfo 座舱信息结构体。
// 描述一个智能座舱的基本元数据，由 Go 网关原生返回（与 Python CockpitManager 保持一致）。
//
// 字段说明:
//   - CockpitID:      座舱唯一标识（如 "cockpit-01"）
//   - Name:           座舱显示名称（如 "座舱1"）
//   - UserID:         绑定用户 ID
//   - RedisDB:        该座舱独占的 Redis 数据库编号
//   - IsActive:       座舱是否处于活跃状态
//   - ThemeColor:     前端主题色（十六进制色值）
type CockpitInfo struct {
	CockpitID   string `json:"cockpit_id"`
	Name        string `json:"name"`
	UserID      string `json:"user_id"`
	RedisDB     int    `json:"redis_db"`
	IsActive    bool   `json:"is_active"`
	ThemeColor  string `json:"theme_color"`
}

// ============================================================
// 中间件状态检查
// ============================================================

// checkTCP 通过 TCP 拨号检查目标端口的连通性。
// 超时时间固定为 3 秒，返回连接延迟（毫秒）和可能的错误。
//
// 参数:
//   - host: 目标主机地址（如 "127.0.0.1"）
//   - port: 目标端口（如 6379）
//
// 返回值:
//   - latency: TCP 连接耗时（毫秒），无论成功失败都会返回
//   - err:     连接失败时的错误对象
func checkTCP(host string, port int) (int64, error) {
	addr := fmt.Sprintf("%s:%d", host, port)
	start := time.Now()
	conn, err := net.DialTimeout("tcp", addr, 3*time.Second)
	latency := time.Since(start).Milliseconds()
	if err != nil {
		return latency, err
	}
	conn.Close()
	return latency, nil
}

// middlewareCheckTarget 描述一次 TCP 连通性检查的目标。
type middlewareCheckTarget struct {
	name string
	host string
	port int
}

// GetAllMiddlewareStatus 检查所有中间件状态
//
// 通过循环遍历中间件列表执行 TCP 拨号，避免逐个手写重复代码。
func GetAllMiddlewareStatus(c *gin.Context) {
	cfg := config.Get()

	// 中间件检查列表 — 新增中间件只需在此追加一行
	checks := []middlewareCheckTarget{
		{"redis", cfg.RedisHost, cfg.RedisPort},
		{"mysql", cfg.MySQLHost, cfg.MySQLPort},
		{"milvus", cfg.MilvusHost, cfg.MilvusPort},
		{"neo4j", cfg.Neo4jHost, cfg.Neo4jPort},
		{"python_ai", cfg.AIHost, cfg.AIPort},
	}

	statuses := make([]MiddlewareStatus, 0, len(checks))
	for _, ck := range checks {
		latency, err := checkTCP(ck.host, ck.port)
		st := MiddlewareStatus{Name: ck.name, Latency: latency}
		if err != nil {
			st.Status = "offline"
			st.Error = err.Error()
		} else {
			st.Status = "online"
		}
		statuses = append(statuses, st)
	}

	// 转为 map 便于前端使用
	result := make(map[string]MiddlewareStatus)
	onlineCount := 0
	for _, s := range statuses {
		result[s.Name] = s
		if s.Status == "online" {
			onlineCount++
		}
	}

	c.JSON(200, gin.H{
		"total":       len(statuses),
		"online":      onlineCount,
		"offline":     len(statuses) - onlineCount,
		"middlewares": result,
		"check_time":  time.Now().Format(time.RFC3339),
	})
}

// GetSingleMiddlewareStatus 检查单个中间件状态
func GetSingleMiddlewareStatus(c *gin.Context) {
	name := c.Param("name")
	cfg := config.Get()

	var status MiddlewareStatus
	status.Name = name

	switch name {
	case "redis":
		latency, err := checkTCP(cfg.RedisHost, cfg.RedisPort)
		status.Latency = latency
		if err != nil {
			status.Status = "offline"
			status.Error = err.Error()
		} else {
			status.Status = "online"
		}
	case "mysql":
		latency, err := checkTCP(cfg.MySQLHost, cfg.MySQLPort)
		status.Latency = latency
		if err != nil {
			status.Status = "offline"
			status.Error = err.Error()
		} else {
			status.Status = "online"
		}
	case "milvus":
		latency, err := checkTCP(cfg.MilvusHost, cfg.MilvusPort)
		status.Latency = latency
		if err != nil {
			status.Status = "offline"
			status.Error = err.Error()
		} else {
			status.Status = "online"
		}
	case "neo4j":
		latency, err := checkTCP(cfg.Neo4jHost, cfg.Neo4jPort)
		status.Latency = latency
		if err != nil {
			status.Status = "offline"
			status.Error = err.Error()
		} else {
			status.Status = "online"
		}
	default:
		c.JSON(404, gin.H{"error": "UNKNOWN_MIDDLEWARE", "message": fmt.Sprintf("Middleware '%s' not found", name)})
		return
	}

	c.JSON(200, status)
}

// ============================================================
// 数据中台 API（Go 原生查 Redis）
// ============================================================

// GetDataPlatformOverview 从 Redis 获取基本统计数据
func GetDataPlatformOverview(c *gin.Context) {
	cfg := config.Get()

	// 尝试从 Redis 获取统计数据
	redisClient := NewRedisClient(cfg.RedisHost, cfg.RedisPort, cfg.RedisPassword, 0)
	defer redisClient.Close()

	totalChats := 0
	totalVehicleCmds := 0
	cacheHits := 0
	cacheMisses := 0
	totalLatencyMs := 0
	latencyCount := 0
	alertCount24h := 0

	// 遍历每个座舱的统计数据
	for i := 1; i <= cfg.CockpitCount; i++ {
		cockpitID := fmt.Sprintf("cockpit-0%d", i)

		// 查询座舱统计 key
		if chatCount, err := redisClient.GetInt(fmt.Sprintf("%s:stats:chat_count", cockpitID)); err == nil {
			totalChats += chatCount
		}
		if vehicleCmdCount, err := redisClient.GetInt(fmt.Sprintf("%s:stats:vehicle_cmd_count", cockpitID)); err == nil {
			totalVehicleCmds += vehicleCmdCount
		}
		if hits, err := redisClient.GetInt(fmt.Sprintf("%s:stats:cache_hits", cockpitID)); err == nil {
			cacheHits += hits
		}
		if misses, err := redisClient.GetInt(fmt.Sprintf("%s:stats:cache_misses", cockpitID)); err == nil {
			cacheMisses += misses
		}
		if latency, err := redisClient.GetInt(fmt.Sprintf("%s:stats:total_latency_ms", cockpitID)); err == nil {
			totalLatencyMs += latency
		}
		if lCount, err := redisClient.GetInt(fmt.Sprintf("%s:stats:latency_count", cockpitID)); err == nil {
			latencyCount += lCount
		}
		if alerts, err := redisClient.GetInt(fmt.Sprintf("%s:stats:alert_count_24h", cockpitID)); err == nil {
			alertCount24h += alerts
		}
	}

	cacheHitRate := 0.0
	if cacheHits+cacheMisses > 0 {
		cacheHitRate = float64(cacheHits) / float64(cacheHits+cacheMisses)
	}

	avgLatencyMs := 0
	if latencyCount > 0 {
		avgLatencyMs = totalLatencyMs / latencyCount
	}

	c.JSON(200, gin.H{
		"total_chats":          totalChats,
		"total_vehicle_cmds":   totalVehicleCmds,
		"cache_hit_rate":       cacheHitRate,
		"avg_latency_ms":       avgLatencyMs,
		"cockpit_count":        cfg.CockpitCount,
		"alert_count_24h":      alertCount24h,
		"current_concurrency":  int64(queryPrometheus(cfg.PrometheusURL, "nexus_active_connections", 0)),
		"source":               "go_native",
	})
}

// GetDataPlatformConcurrency 返回并发指标
//
// 通过 Prometheus HTTP API 查询实时并发连接数和 QPS，
// 替代原来硬编码返回 0 的占位逻辑。
func GetDataPlatformConcurrency(c *gin.Context) {
	cfg := config.Get()

	// 从 Prometheus 查询实时指标
	currentConcurrency := queryPrometheus(cfg.PrometheusURL, "nexus_active_connections", 0)
	qps := queryPrometheus(cfg.PrometheusURL, "sum(rate(nexus_requests_total[1m]))", 0)
	peakConcurrency := queryPrometheus(cfg.PrometheusURL, "max_over_time(nexus_active_connections[24h])", 0)

	c.JSON(200, gin.H{
		"current_concurrency":  int64(currentConcurrency),
		"qps":                 int64(qps),
		"peak_concurrency_24h": int64(peakConcurrency),
		"cockpit_count":       cfg.CockpitCount,
		"per_cockpit":         queryPrometheusPerCockpit(cfg.PrometheusURL,
				"nexus_active_connections{cockpit_id=\"%s\"}", cfg.CockpitCount),
		"source":              "go_native_prometheus",
	})
}

// GetDataPlatformAlerts 返回告警历史
func GetDataPlatformAlerts(c *gin.Context) {
	cfg := config.Get()

	// 尝试从 Redis 获取告警历史
	redisClient := NewRedisClient(cfg.RedisHost, cfg.RedisPort, cfg.RedisPassword, 0)
	defer redisClient.Close()

	alerts := []map[string]interface{}{}

	// 遍历每个座舱的告警
	for i := 1; i <= cfg.CockpitCount; i++ {
		cockpitID := fmt.Sprintf("cockpit-0%d", i)
		alertKey := fmt.Sprintf("%s:alerts", cockpitID)

		// 尝试获取最近告警列表（Demo: 简化处理）
		if alertJSON, err := redisClient.Get(alertKey); err == nil && alertJSON != "" {
			var cockpitAlerts []map[string]interface{}
			if err := json.Unmarshal([]byte(alertJSON), &cockpitAlerts); err == nil {
				alerts = append(alerts, cockpitAlerts...)
			}
		}
	}

	c.JSON(200, gin.H{
		"total":  len(alerts),
		"alerts": alerts,
		"source": "go_native",
	})
}


// ============================================================
// 座舱列表（Go 原生返回配置）
// ============================================================

// ListCockpits 返回座舱列表（Go 原生）
//
// 主题色和座舱名称从配置读取（COCKPIT_THEMES / COCKPIT_NAMES 环境变量），
// 替代原来硬编码的色值和名称。新增座舱只需修改配置，无需改代码。
func ListCockpits(c *gin.Context) {
	cfg := config.Get()

	// 从配置读取主题色和名称列表
	themes := cfg.CockpitThemeList()
	names := cfg.CockpitNameList()
	if len(themes) == 0 {
		themes = []string{"#4fc3f7"}
	}
	if len(names) == 0 {
		names = []string{"座舱1"}
	}

	cockpits := []CockpitInfo{}
	for i := 1; i <= cfg.CockpitCount; i++ {
		themeIdx := (i - 1) % len(themes)
		nameIdx := (i - 1) % len(names)
		cockpits = append(cockpits, CockpitInfo{
			CockpitID:      fmt.Sprintf("cockpit-0%d", i),
			Name:           names[nameIdx],
			UserID:         fmt.Sprintf("user_0%d", i),
			RedisDB:        i,
			IsActive:       true,
			ThemeColor:     themes[themeIdx],
		})
	}

	c.JSON(200, gin.H{
		"total":    len(cockpits),
		"active":   len(cockpits),
		"cockpits": cockpits,
		"source":   "go_native",
	})
}

// ============================================================
// 健康检查（增强版，包含中间件状态）
// ============================================================

// HealthCheck 增强版健康检查
func HealthCheck(c *gin.Context) {
	cfg := config.Get()

	// 检查 Python AI 服务
	_, aiErr := checkTCP(cfg.AIHost, cfg.AIPort)
	aiStatus := "online"
	if aiErr != nil {
		aiStatus = "offline"
	}

	// 检查 Redis
	_, redisErr := checkTCP(cfg.RedisHost, cfg.RedisPort)
	redisStatus := "online"
	if redisErr != nil {
		redisStatus = "offline"
	}

	overallStatus := "healthy"
	if aiStatus == "offline" {
		overallStatus = "degraded"
	}
	if aiStatus == "offline" && redisStatus == "offline" {
		overallStatus = "offline"
	}

	c.JSON(200, gin.H{
		"status":        overallStatus,
		"service":       "nexus_gate",
		"version":       "v2.1",
		"mode":          cfg.GateMode,
		"cockpit_count": cfg.CockpitCount,
		"services": gin.H{
			"redis":     redisStatus,
			"python_ai": aiStatus,
		},
	})
}

// ============================================================
// 辅助函数
// ============================================================

// RespondJSON 向 HTTP 响应写入 JSON 数据，用于非 Gin 场景（如 WebSocket 处理器）。
//
// 参数:
//   - w:      http.ResponseWriter
//   - status: HTTP 状态码（如 200、404、500）
//   - data:   要序列化为 JSON 的数据对象
func RespondJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}
