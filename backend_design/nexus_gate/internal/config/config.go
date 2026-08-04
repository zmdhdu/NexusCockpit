// Copyright (c) 2026 zhangmengdi (NexusCockpit)
// Licensed under the MIT License. See LICENSE in the project root for details.
// Source: https://github.com/zmdhdu/NexusCockpit

// Package config — NexusGate 配置加载
//
// 从环境变量 / .env 文件加载 Go 网关配置。
// 复用与 Python 相同的 .env 文件。
package config

import (
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
)

// Config 全局配置
type Config struct {
	// Go 网关
	GateHost string
	GatePort int

	// Python AI 服务
	AIHost string
	AIPort int

	// 网关模式: proxy / grpc
	GateMode string

	// JWT
	JWTSecret      string
	JWTExpireHours int

	// Redis
	RedisHost     string
	RedisPort     int
	RedisPassword string
	RedisDB       int

	// RBAC
	DefaultRole   string
	AdminUsername string
	AdminPassword string
	// 普通用户签发 Token 的共享口令（空 = 不校验，仅限开发环境；生产环境必须设置）
	UserPassword string

	// CORS
	CORSOrigins string

	// 限流
	RateLimitQPS int

	// 座舱
	CockpitCount int

	// 中间件（用于 Go 原生健康检查）
	MySQLHost string
	MySQLPort int
	MilvusHost string
	MilvusPort int
	Neo4jHost  string
	Neo4jPort  int

	// 声纹
	VoiceprintThreshold float64

	// 可观测性 — Prometheus 查询地址（用于 Go 端查询并发/QPS 等指标）
	PrometheusURL string

	// 座舱主题色（逗号分隔，按 COCKPIT_COUNT 循环取色）
	CockpitThemes string
	// 座舱显示名称（逗号分隔，按 COCKPIT_COUNT 循环取名）
	CockpitNames string
}

var cfg *Config

// Load 加载配置（从环境变量）
func Load() *Config {
	cfg = &Config{
		GateHost: getEnv("NEXUS_GATE_HOST", "0.0.0.0"),
		GatePort: getEnvInt("NEXUS_GATE_PORT", 8080),
		AIHost:   getEnv("NEXUS_AI_HOST", "127.0.0.1"),
		AIPort:   getEnvInt("NEXUS_AI_PORT", 8000),
		GateMode: getEnv("NEXUS_GATE_MODE", "proxy"),
		// JWT 密钥：优先 JWT_SECRET，未设置时复用 Python 侧的 JWT_SECRET_KEY，
		// 确保双端互验 Token（网关签发 → Python 验证，反之亦然）
		// JWT 密钥: 优先 JWT_SECRET, 未设置时复用 Python 侧的 JWT_SECRET_KEY
		// 安全: 留空则启动时自动生成随机密钥 (仅开发环境)
		JWTSecret:           getEnv("JWT_SECRET", getEnv("JWT_SECRET_KEY", "")),
		JWTExpireHours:      getEnvInt("JWT_EXPIRE_HOURS", 24),
		RedisHost:           getEnv("REDIS_HOST", "127.0.0.1"),
		RedisPort:           getEnvInt("REDIS_PORT", 16379),
		RedisPassword:       getEnv("REDIS_PASSWORD", ""),
		RedisDB:             getEnvInt("REDIS_DB", 0),
		DefaultRole:         getEnv("RBAC_DEFAULT_ROLE", "cockpit_user"),
		AdminUsername:       getEnv("RBAC_ADMIN_USERNAME", "admin"),
		AdminPassword:       getEnv("RBAC_ADMIN_PASSWORD", ""),
		UserPassword:        getEnv("RBAC_USER_PASSWORD", ""),
		CORSOrigins:         getEnv("CORS_ORIGINS", "*"),
		RateLimitQPS:        getEnvInt("RATE_LIMIT_QPS", 100),
		CockpitCount:        getEnvInt("COCKPIT_COUNT", 1),
		MySQLHost:           getEnv("MYSQL_HOST", "127.0.0.1"),
		MySQLPort:           getEnvInt("MYSQL_PORT", 13306),
		MilvusHost:          getEnv("MILVUS_HOST", "127.0.0.1"),
		MilvusPort:          getEnvInt("MILVUS_PORT", 19530),
		Neo4jHost:           getEnv("NEO4J_HOST", "127.0.0.1"),
		Neo4jPort:           getEnvInt("NEO4J_BOLT_PORT", 17687),
		VoiceprintThreshold: getEnvFloat("VOICEPRINT_THRESHOLD", 0.7),
		PrometheusURL:      getEnv("PROMETHEUS_URL", "http://127.0.0.1:9200"),
		CockpitThemes:      getEnv("COCKPIT_THEMES", "#4fc3f7,#66bb6a,#ab47bc"),
		CockpitNames:       getEnv("COCKPIT_NAMES", "座舱1,座舱2,座舱3"),
	}
	validateProdSecurity(cfg)
	return cfg
}

// validateProdSecurity 生产环境安全检查（与 Python 侧 config/__init__.py 对齐）：
// APP_ENV=prod 时检测到默认弱密钥/弱口令/CORS 通配符直接拒绝启动。
func validateProdSecurity(c *Config) {
	if os.Getenv("APP_ENV") != "prod" {
		return
	}
	var errs []string
	if c.JWTSecret == "" || c.JWTSecret == "nexus-cockpit-secret" {
		errs = append(errs, "JWT_SECRET 未设置或为默认弱密钥，生产环境必须设置强随机密钥")
	}
	if c.AdminPassword != "" && c.AdminPassword == "admin123" {
		errs = append(errs, "RBAC_ADMIN_PASSWORD 仍为默认弱口令，生产环境必须修改")
	}
	if c.CORSOrigins == "*" {
		errs = append(errs, "CORS_ORIGINS 为 '*' (允许所有域)，生产环境必须指定具体域名")
	}
	if c.UserPassword == "" {
		errs = append(errs, "RBAC_USER_PASSWORD 未设置，生产环境普通用户签发 Token 必须校验凭证")
	}
	if len(errs) > 0 {
		log.Fatalf("[生产环境安全拒绝] 检测到致命安全配置错误，拒绝启动:\n  - %s", strings.Join(errs, "\n  - "))
	}
}

// AllowedOrigins 返回 CORS 白名单列表；["*"] 表示允许所有来源（仅开发环境）
func (c *Config) AllowedOrigins() []string {
	parts := strings.Split(c.CORSOrigins, ",")
	origins := make([]string, 0, len(parts))
	for _, p := range parts {
		if s := strings.TrimSpace(p); s != "" {
			origins = append(origins, s)
		}
	}
	return origins
}

// CockpitThemeList 返回座舱主题色列表（逗号分隔 → 切片）
func (c *Config) CockpitThemeList() []string {
	return splitTrim(c.CockpitThemes)
}

// CockpitNameList 返回座舱名称列表（逗号分隔 → 切片）
func (c *Config) CockpitNameList() []string {
	return splitTrim(c.CockpitNames)
}

// Get 获取全局配置
func Get() *Config {
	if cfg == nil {
		Load()
	}
	return cfg
}

// AIBaseURL 返回 Python AI 服务的基地址
func (c *Config) AIBaseURL() string {
	return fmt.Sprintf("http://%s:%d", c.AIHost, c.AIPort)
}

// getEnv 从环境变量读取字符串，不存在时返回默认值
func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

// getEnvInt 从环境变量读取整数，不存在或格式错误时返回默认值
func getEnvInt(key string, defaultVal int) int {
	if val := os.Getenv(key); val != "" {
		if n, err := strconv.Atoi(val); err == nil {
			return n
		}
	}
	return defaultVal
}

// getEnvFloat 从环境变量读取浮点数，不存在或格式错误时返回默认值
func getEnvFloat(key string, defaultVal float64) float64 {
	if val := os.Getenv(key); val != "" {
		if f, err := strconv.ParseFloat(val, 64); err == nil {
			return f
		}
	}
	return defaultVal
}

// splitTrim 内部辅助函数：逗号分隔字符串 → 去空格切片
func splitTrim(s string) []string {
	parts := strings.Split(s, ",")
	result := make([]string, 0, len(parts))
	for _, p := range parts {
		if v := strings.TrimSpace(p); v != "" {
			result = append(result, v)
		}
	}
	return result
}
