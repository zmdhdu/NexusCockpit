// Copyright (c) 2026 zhangmengdi (NexusCockpit)
// Licensed under the MIT License. See LICENSE in the project root for details.
// Source: https://github.com/zmdhdu/NexusCockpit

// Package router — Gin 路由分发
//
// 路由分两类:
// 1. Go 原生处理: 非AI请求（health/auth/dataplatform/middleware/settings）
// 2. 转发 Python: AI请求（cockpit chat/vehicle/asr/tts/ws）
package router

import (
	"fmt"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"nexus_gate/internal/auth"
	"nexus_gate/internal/config"
	"nexus_gate/internal/handlers"
	"nexus_gate/internal/proxy"
	"nexus_gate/internal/ratelimit"
	"nexus_gate/internal/ws"
)

// Prometheus 指标
var (
	httpRequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "nexus_gate_http_requests_total",
			Help: "Total number of HTTP requests processed by NexusGate",
		},
		[]string{"method", "path", "status", "cockpit_id"},
	)
	httpRequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "nexus_gate_http_request_duration_seconds",
			Help:    "HTTP request duration in seconds",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"method", "path"},
	)
	wsActiveConnections = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "nexus_gate_ws_active_connections",
			Help: "Number of active WebSocket connections",
		},
		[]string{"cockpit_id"},
	)
)

// SetupRouter 配置 Gin 路由
func SetupRouter(hub *ws.Hub, limiter *ratelimit.RateLimiter) *gin.Engine {
	cfg := config.Get()

	if cfg.GateMode == "proxy" {
		gin.SetMode(gin.ReleaseMode)
	} else {
		gin.SetMode(gin.DebugMode)
	}

	r := gin.Default()

	// CORS 中间件
	r.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})

	// Prometheus 指标中间件 — 记录每个请求的耗时和状态
	r.Use(func(c *gin.Context) {
		start := time.Now()
		c.Next()
		duration := time.Since(start).Seconds()

		cockpitID := c.Param("cockpit_id")
		if cockpitID == "" {
			cockpitID = "global"
		}

		// 截断 path，避免高基数问题
		path := c.FullPath()
		if path == "" {
			path = "unknown"
		}

		httpRequestsTotal.WithLabelValues(c.Request.Method, path, fmt.Sprintf("%d", c.Writer.Status()), cockpitID).Inc()
		httpRequestDuration.WithLabelValues(c.Request.Method, path).Observe(duration)
	})

	// ==================== Go 原生处理（无需 AI）====================

	// Prometheus 指标端点
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// 健康检查（Go 原生，增强版含中间件状态）
	r.GET("/health", handlers.HealthCheck)

	// JWT Token 签发（公开端点）
	r.POST("/auth/token", handleTokenIssue)

	// 数据中台 API — Go 原生处理（查 Redis/配置）+ 部分 Python 转发
	dataplatform := r.Group("/dataplatform", OptionalAuthMiddleware())
	{
		// Go 原生: 基本统计概览（查 Redis）
		dataplatform.GET("/overview", handlers.GetDataPlatformOverview)
		// Go 原生: 并发指标
		dataplatform.GET("/concurrency", handlers.GetDataPlatformConcurrency)
		// Go 原生: 告警历史（查 Redis）
		dataplatform.GET("/alerts", handlers.GetDataPlatformAlerts)
		// 转发 Python: 单座舱详细数据（需要 Python 聚合）
		dataplatform.GET("/cockpit/:cockpit_id", proxyToPython)
		// 转发 Python: Agent 活动日志（需要 Python 查 MySQL）
		dataplatform.GET("/agent/activity", proxyToPython)
		// 转发 Python: 座舱对比（需要 Python 聚合）
		dataplatform.GET("/comparison", proxyToPython)
	}

	// 中间件状态 API — Go 原生处理（TCP 端口连通性检查）
	middlewareGroup := r.Group("/middleware", OptionalAuthMiddleware())
	{
		middlewareGroup.GET("/", handlers.GetAllMiddlewareStatus)
		middlewareGroup.GET("/:name", handlers.GetSingleMiddlewareStatus)
	}

	// 设置中心 API — Go 原生处理座舱列表，其余转发 Python
	settingsGroup := r.Group("/settings", AuthMiddleware())
	{
		// Go 原生: 座舱列表（从配置返回）
		settingsGroup.GET("/cockpits", handlers.ListCockpits)
		// 转发 Python: 座舱 CRUD 写操作（需要 MySQL）
		settingsGroup.POST("/cockpits", RequireRole("super_admin", "cockpit_admin"), proxyToPython)
		settingsGroup.PUT("/cockpits/:cockpit_id", RequireRole("super_admin", "cockpit_admin"), proxyToPython)
		settingsGroup.DELETE("/cockpits/:cockpit_id", RequireRole("super_admin"), proxyToPython)
		// 转发 Python: 用户管理（需要 MySQL）
		settingsGroup.GET("/users", RequireRole("super_admin", "cockpit_admin"), proxyToPython)
		settingsGroup.POST("/users", RequireRole("super_admin", "cockpit_admin"), proxyToPython)
		// 转发 Python: 中间件配置（需要 MySQL）
		settingsGroup.GET("/middleware", RequireRole("super_admin"), proxyToPython)
		settingsGroup.PUT("/middleware", RequireRole("super_admin"), proxyToPython)
		// 转发 Python: 声纹注册/验证（需要 AI 模型）
		settingsGroup.GET("/voiceprint/status", proxyToPython)
		settingsGroup.POST("/voiceprint/enroll", proxyToPython)
		settingsGroup.POST("/voiceprint/verify", proxyToPython)
		settingsGroup.DELETE("/voiceprint/:user_id", proxyToPython)
	}

	// ==================== 需要 AI 的请求（转发到 Python）====================

	// 座舱 API — 需要 JWT 鉴权 + 限流
	cockpit := r.Group("/cockpit/:cockpit_id", AuthMiddleware(), RateLimitMiddleware(limiter))
	{
		// 状态查询（Go 可直接查 Redis，Demo 转发 Python）
		cockpit.GET("/status", proxyToPython)

		// 对话（需要 AI）
		cockpit.POST("/chat", proxyToPython)
		cockpit.POST("/chat/stream", proxyToPython)

		// 车控（需要 AI）
		cockpit.POST("/vehicle/cmd", proxyToPython)
		cockpit.GET("/vehicle/status", proxyToPython)

		// ASR / TTS（需要 AI）
		cockpit.POST("/asr", proxyToPython)
		cockpit.POST("/tts", proxyToPython)
	}

	// WebSocket — 座舱对话（需要 JWT 鉴权）
	r.GET("/cockpit/:cockpit_id/ws/chat", AuthMiddleware(), func(c *gin.Context) {
		cockpitID := c.Param("cockpit_id")
		userID, _ := c.Get("user_id")
		userIDStr, _ := userID.(string)
		if userIDStr == "" {
			userIDStr = "anonymous"
		}
		wsActiveConnections.WithLabelValues(cockpitID).Inc()
		hub.HandleWebSocket(c.Writer, c.Request, cockpitID, userIDStr)
		wsActiveConnections.WithLabelValues(cockpitID).Dec()
	})

	// WebSocket — 数据中台实时推送
	r.GET("/dataplatform/ws/realtime", OptionalAuthMiddleware(), func(c *gin.Context) {
		wsActiveConnections.WithLabelValues("dataplatform").Inc()
		hub.HandleWebSocket(c.Writer, c.Request, "dataplatform", "viewer")
		wsActiveConnections.WithLabelValues("dataplatform").Dec()
	})

	return r
}

// proxyToPython 将请求转发到 Python AI 服务
func proxyToPython(c *gin.Context) {
	if proxy.ReverseProxy == nil {
		c.JSON(503, gin.H{"error": "PROXY_NOT_INITIALIZED", "message": "Reverse proxy not initialized"})
		return
	}

	// 优先使用 JWT claims 中的 cockpit_id（已通过 AuthMiddleware 校验）
	// 仅当 JWT 中 cockpit_id 为空（如 admin 用户）时，才回退到 URL path
	jwtCockpitID := ""
	jwtUserID := ""
	jwtRole := ""

	if claims, exists := c.Get("claims"); exists {
		if cl, ok := claims.(*auth.Claims); ok {
			jwtCockpitID = cl.CockpitID
			jwtUserID = cl.UserID
			jwtRole = cl.Role
		}
	}

	// cockpit_id 解析优先级: JWT > URL path > 空
	// 对座舱级路由 (/cockpit/:cockpit_id/...)，AuthMiddleware 已校验 URL path 与 JWT 匹配
	// 对非座舱路由 (/dataplatform/cockpit/:cockpit_id 等)，JWT 为空时用 URL path
	finalCockpitID := jwtCockpitID
	if finalCockpitID == "" {
		finalCockpitID = c.Param("cockpit_id")
	}

	c.Request.Header.Set("X-Cockpit-Id", finalCockpitID)
	c.Request.Header.Set("X-User-Id", jwtUserID)
	c.Request.Header.Set("X-User-Role", jwtRole)

	proxy.ReverseProxy.ServeHTTP(c.Writer, c.Request)
}

// handleTokenIssue JWT Token 签发
func handleTokenIssue(c *gin.Context) {
	var req struct {
		UserID   string `json:"user_id"`
		Password string `json:"password"`
		CockpitID string `json:"cockpit_id"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": "INVALID_REQUEST", "message": err.Error()})
		return
	}

	if req.UserID == "" {
		c.JSON(400, gin.H{"error": "MISSING_USER_ID", "message": "user_id is required"})
		return
	}

	// 设置默认值
	cockpitID := req.CockpitID
	if cockpitID == "" {
		cockpitID = "cockpit-01"
	}
	role := "cockpit_user"

	// Admin 用户特殊处理
	cfg := config.Get()
	if req.UserID == cfg.AdminUsername {
		role = "super_admin"
		cockpitID = "" // admin 不绑定座舱
	}

	// 签发 Token
	token, err := auth.GenerateToken(req.UserID, cockpitID, role, req.UserID)
	if err != nil {
		c.JSON(500, gin.H{"error": "TOKEN_GENERATION_FAILED", "message": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"access_token": token,
		"token_type":   "Bearer",
		"user_id":      req.UserID,
		"cockpit_id":   cockpitID,
		"role":         role,
	})
}

// AuthMiddleware JWT 鉴权中间件（必须携带有效 Token）
func AuthMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.JSON(401, gin.H{"error": "MISSING_TOKEN", "message": "Authorization header is required"})
			c.Abort()
			return
		}

		claims, err := auth.ParseToken(authHeader)
		if err != nil {
			c.JSON(401, gin.H{"error": "INVALID_TOKEN", "message": err.Error()})
			c.Abort()
			return
		}

		// 校验座舱访问权限
		cockpitID := c.Param("cockpit_id")
		if cockpitID != "" {
			if err := auth.ValidateCockpitAccess(claims, cockpitID); err != nil {
				c.JSON(403, gin.H{"error": "ACCESS_DENIED", "message": err.Error()})
				c.Abort()
				return
			}
		}

		// 将 claims 存入 context
		c.Set("claims", claims)
		c.Set("user_id", claims.UserID)
		c.Set("cockpit_id", claims.CockpitID)
		c.Set("role", claims.Role)

		c.Next()
	}
}

// OptionalAuthMiddleware 可选 JWT 鉴权中间件（有 Token 则解析，无 Token 也放行）
// 用于 dataplatform/middleware 等查看类接口，无 Token 时仍可查看（降级模式）
func OptionalAuthMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.Set("user_id", "anonymous")
			c.Set("cockpit_id", "")
			c.Set("role", "cockpit_viewer")
			c.Next()
			return
		}

		claims, err := auth.ParseToken(authHeader)
		if err != nil {
			// Token 无效时降级为匿名用户
			c.Set("user_id", "anonymous")
			c.Set("cockpit_id", "")
			c.Set("role", "cockpit_viewer")
			c.Next()
			return
		}

		c.Set("claims", claims)
		c.Set("user_id", claims.UserID)
		c.Set("cockpit_id", claims.CockpitID)
		c.Set("role", claims.Role)

		c.Next()
	}
}

// RequireRole 角色校验中间件（仅允许指定角色通过）
func RequireRole(roles ...string) gin.HandlerFunc {
	return func(c *gin.Context) {
		role, exists := c.Get("role")
		if !exists {
			c.JSON(403, gin.H{"error": "FORBIDDEN", "message": "No role found in context"})
			c.Abort()
			return
		}

		userRole, ok := role.(string)
		if !ok {
			c.JSON(403, gin.H{"error": "FORBIDDEN", "message": "Invalid role type"})
			c.Abort()
			return
		}

		for _, r := range roles {
			if userRole == r {
				c.Next()
				return
			}
		}

		c.JSON(403, gin.H{"error": "FORBIDDEN", "message": fmt.Sprintf("Role '%s' is not allowed", userRole)})
		c.Abort()
	}
}

// RateLimitMiddleware 座舱级优先级限流中间件
// 根据请求路径自动判断优先级:
//   - /vehicle/cmd, /asr, /tts → PriorityHigh（实时性要求高）
//   - /chat, /chat/stream → PriorityNormal（默认）
//   - /status, /vehicle/status → PriorityLow（非实时查询）
func RateLimitMiddleware(limiter *ratelimit.RateLimiter) gin.HandlerFunc {
	return func(c *gin.Context) {
		cockpitID := c.Param("cockpit_id")
		if cockpitID == "" {
			cockpitID = "default"
		}

		// 根据请求路径推断优先级
		priority := ratelimit.PriorityNormal // 默认普通优先级
		path := c.Request.URL.Path

		if strings.Contains(path, "/vehicle/cmd") ||
			strings.Contains(path, "/asr") ||
			strings.Contains(path, "/tts") {
			priority = ratelimit.PriorityHigh
		} else if strings.Contains(path, "/status") {
			priority = ratelimit.PriorityLow
		}

		if !limiter.AllowWithPriority(cockpitID, priority) {
			c.JSON(429, gin.H{
				"error":    "RATE_LIMITED",
				"message":  fmt.Sprintf("Cockpit %s rate limit exceeded (priority=%d)", cockpitID, priority),
				"priority": priority,
			})
			c.Abort()
			return
		}

		c.Next()
	}
}

// GetCockpitIDFromPath 从 URL path 中提取 cockpit_id
func GetCockpitIDFromPath(path string) string {
	// /cockpit/cockpit-01/chat → cockpit-01
	parts := strings.Split(path, "/")
	for i, p := range parts {
		if p == "cockpit" && i+1 < len(parts) {
			return parts[i+1]
		}
	}
	return ""
}
