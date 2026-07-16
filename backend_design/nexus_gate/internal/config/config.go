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
	"os"
	"strconv"
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
	JWTSecret     string
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

	// CORS
	CORSOrigins string

	// 限流
	RateLimitQPS int

	// 座舱
	CockpitCount     int
	IsolationMode    string
	SubAgentCheckMin int
	SubAgentCheckMax int

	// 声纹
	VoiceprintThreshold float64
}

var cfg *Config

// Load 加载配置（从环境变量）
func Load() *Config {
	cfg = &Config{
		GateHost:            getEnv("NEXUS_GATE_HOST", "0.0.0.0"),
		GatePort:            getEnvInt("NEXUS_GATE_PORT", 8080),
		AIHost:              getEnv("NEXUS_AI_HOST", "127.0.0.1"),
		AIPort:              getEnvInt("NEXUS_AI_PORT", 8000),
		GateMode:            getEnv("NEXUS_GATE_MODE", "proxy"),
		JWTSecret:           getEnv("JWT_SECRET", "nexus-cockpit-v2.1"),
		JWTExpireHours:      getEnvInt("JWT_EXPIRE_HOURS", 24),
		RedisHost:           getEnv("REDIS_HOST", "127.0.0.1"),
		RedisPort:           getEnvInt("REDIS_PORT", 6379),
		RedisPassword:       getEnv("REDIS_PASSWORD", ""),
		RedisDB:             getEnvInt("REDIS_DB", 0),
		DefaultRole:         getEnv("RBAC_DEFAULT_ROLE", "cockpit_user"),
		AdminUsername:       getEnv("RBAC_ADMIN_USERNAME", "admin"),
		AdminPassword:       getEnv("RBAC_ADMIN_PASSWORD", "admin123"),
		CORSOrigins:         getEnv("CORS_ORIGINS", "*"),
		RateLimitQPS:        getEnvInt("RATE_LIMIT_QPS", 100),
		CockpitCount:        getEnvInt("COCKPIT_COUNT", 3),
		IsolationMode:       getEnv("COCKPIT_ISOLATION_MODE", "shared"),
		SubAgentCheckMin:    getEnvInt("SUBAGENT_CHECK_MIN", 30),
		SubAgentCheckMax:    getEnvInt("SUBAGENT_CHECK_MAX", 60),
		VoiceprintThreshold: getEnvFloat("VOICEPRINT_THRESHOLD", 0.7),
	}
	return cfg
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
