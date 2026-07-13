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
	"os"
	"strconv"
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
//   - SubAgentStatus: 子 Agent 运行状态（"running"/"stopped"）
type CockpitInfo struct {
	CockpitID   string `json:"cockpit_id"`
	Name        string `json:"name"`
	UserID      string `json:"user_id"`
	RedisDB     int    `json:"redis_db"`
	IsActive    bool   `json:"is_active"`
	ThemeColor  string `json:"theme_color"`
	SubAgentStatus string `json:"subagent_status"`
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

// GetAllMiddlewareStatus 检查所有中间件状态
func GetAllMiddlewareStatus(c *gin.Context) {
	cfg := config.Get()
	statuses := []MiddlewareStatus{}

	// Redis
	redisLatency, redisErr := checkTCP(cfg.RedisHost, cfg.RedisPort)
	redisStatus := MiddlewareStatus{
		Name: "redis", Latency: redisLatency,
	}
	if redisErr != nil {
		redisStatus.Status = "offline"
		redisStatus.Error = redisErr.Error()
	} else {
		redisStatus.Status = "online"
	}
	statuses = append(statuses, redisStatus)

	// MySQL
	mysqlHost := getEnv("MYSQL_HOST", "127.0.0.1")
	mysqlPort := getEnvInt("MYSQL_PORT", 3306)
	mysqlLatency, mysqlErr := checkTCP(mysqlHost, mysqlPort)
	mysqlStatus := MiddlewareStatus{
		Name: "mysql", Latency: mysqlLatency,
	}
	if mysqlErr != nil {
		mysqlStatus.Status = "offline"
		mysqlStatus.Error = mysqlErr.Error()
	} else {
		mysqlStatus.Status = "online"
	}
	statuses = append(statuses, mysqlStatus)

	// Milvus
	milvusHost := getEnv("MILVUS_HOST", "127.0.0.1")
	milvusPort := getEnvInt("MILVUS_PORT", 19530)
	milvusLatency, milvusErr := checkTCP(milvusHost, milvusPort)
	milvusStatus := MiddlewareStatus{
		Name: "milvus", Latency: milvusLatency,
	}
	if milvusErr != nil {
		milvusStatus.Status = "offline"
		milvusStatus.Error = milvusErr.Error()
	} else {
		milvusStatus.Status = "online"
	}
	statuses = append(statuses, milvusStatus)

	// Neo4j
	neo4jHost := getEnv("NEO4J_HOST", "127.0.0.1")
	neo4jPort := getEnvInt("NEO4J_BOLT_PORT", 7687)
	neo4jLatency, neo4jErr := checkTCP(neo4jHost, neo4jPort)
	neo4jStatus := MiddlewareStatus{
		Name: "neo4j", Latency: neo4jLatency,
	}
	if neo4jErr != nil {
		neo4jStatus.Status = "offline"
		neo4jStatus.Error = neo4jErr.Error()
	} else {
		neo4jStatus.Status = "online"
	}
	statuses = append(statuses, neo4jStatus)

	// RabbitMQ
	rabbitHost := getEnv("RABBITMQ_HOST", "127.0.0.1")
	rabbitPort := getEnvInt("RABBITMQ_PORT", 5672)
	rabbitLatency, rabbitErr := checkTCP(rabbitHost, rabbitPort)
	rabbitStatus := MiddlewareStatus{
		Name: "rabbitmq", Latency: rabbitLatency,
	}
	if rabbitErr != nil {
		rabbitStatus.Status = "offline"
		rabbitStatus.Error = rabbitErr.Error()
	} else {
		rabbitStatus.Status = "online"
	}
	statuses = append(statuses, rabbitStatus)

	// Python AI 服务
	aiLatency, aiErr := checkTCP(cfg.AIHost, cfg.AIPort)
	aiStatus := MiddlewareStatus{
		Name: "python_ai", Latency: aiLatency,
	}
	if aiErr != nil {
		aiStatus.Status = "offline"
		aiStatus.Error = aiErr.Error()
	} else {
		aiStatus.Status = "online"
	}
	statuses = append(statuses, aiStatus)

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
		latency, err := checkTCP(getEnv("MYSQL_HOST", "127.0.0.1"), getEnvInt("MYSQL_PORT", 3306))
		status.Latency = latency
		if err != nil {
			status.Status = "offline"
			status.Error = err.Error()
		} else {
			status.Status = "online"
		}
	case "milvus":
		latency, err := checkTCP(getEnv("MILVUS_HOST", "127.0.0.1"), getEnvInt("MILVUS_PORT", 19530))
		status.Latency = latency
		if err != nil {
			status.Status = "offline"
			status.Error = err.Error()
		} else {
			status.Status = "online"
		}
	case "neo4j":
		latency, err := checkTCP(getEnv("NEO4J_HOST", "127.0.0.1"), getEnvInt("NEO4J_BOLT_PORT", 7687))
		status.Latency = latency
		if err != nil {
			status.Status = "offline"
			status.Error = err.Error()
		} else {
			status.Status = "online"
		}
	case "rabbitmq":
		latency, err := checkTCP(getEnv("RABBITMQ_HOST", "127.0.0.1"), getEnvInt("RABBITMQ_PORT", 5672))
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
		"current_concurrency":  0, // Demo: 无法从 Go 端获取实时并发
		"source":               "go_native",
	})
}

// GetDataPlatformConcurrency 返回并发指标
func GetDataPlatformConcurrency(c *gin.Context) {
	cfg := config.Get()

	// Demo: 返回基本的并发信息
	// 真正的并发指标应从 Prometheus 获取，这里简化处理
	c.JSON(200, gin.H{
		"current_concurrency": 0,
		"qps":                 0,
		"peak_concurrency_24h": 0,
		"cockpit_count":       cfg.CockpitCount,
		"per_cockpit":         generateCockpitConcurrency(cfg.CockpitCount),
		"source":              "go_native",
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

// generateCockpitConcurrency 生成每个座舱的并发信息列表（Demo 模式）。
// 当前返回的并发数和 QPS 均为 0，实际指标应从 Prometheus 获取。
//
// 参数:
//   - count: 座舱数量
//
// 返回值: 每个座舱的并发信息 map 列表
func generateCockpitConcurrency(count int) []map[string]interface{} {
	result := []map[string]interface{}{}
	for i := 1; i <= count; i++ {
		result = append(result, map[string]interface{}{
			"cockpit_id":          fmt.Sprintf("cockpit-0%d", i),
			"current_concurrency": 0,
			"qps":                 0,
		})
	}
	return result
}

// ============================================================
// 座舱列表（Go 原生返回配置）
// ============================================================

// ListCockpits 返回座舱列表（Go 原生）
func ListCockpits(c *gin.Context) {
	cfg := config.Get()

	// 生成默认座舱列表（与 Python CockpitManager 的默认配置一致）
	themes := []string{"#4fc3f7", "#66bb6a", "#ab47bc"}
	names := []string{"座舱1", "座舱2", "座舱3"}
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
			SubAgentStatus: "running",
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

// getEnv 从环境变量读取字符串，若不存在则返回默认值。
//
// 参数:
//   - key:        环境变量名
//   - defaultVal: 默认值（环境变量未设置或为空时使用）
//
// 返回值: 环境变量值或默认值
func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

// getEnvInt 从环境变量读取整型值，若不存在或解析失败则返回默认值。
//
// 参数:
//   - key:        环境变量名
//   - defaultVal: 默认值（环境变量未设置或解析失败时使用）
//
// 返回值: 解析后的整型值或默认值
func getEnvInt(key string, defaultVal int) int {
	val := os.Getenv(key)
	if val == "" {
		return defaultVal
	}
	n, err := strconv.Atoi(val)
	if err != nil {
		return defaultVal
	}
	return n
}

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
