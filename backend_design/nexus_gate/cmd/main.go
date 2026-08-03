// Copyright (c) 2026 zhangmengdi (NexusCockpit)
// Licensed under the MIT License. See LICENSE in the project root for details.
// Source: https://github.com/zmdhdu/NexusCockpit

// NexusGate — NexusCockpit Go 并发网关
//
// 职责:
// 1. JWT 鉴权 + cockpit_id 校验
// 2. 座舱级令牌桶限流
// 3. 非 AI 请求直接处理（health/auth）
// 4. AI 请求反向代理到 Python FastAPI
// 5. WebSocket Hub 管理千级连接
package main

import (
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"nexus_gate/internal/config"
	"nexus_gate/internal/proxy"
	"nexus_gate/internal/ratelimit"
	"nexus_gate/internal/router"
	"nexus_gate/internal/ws"
)

// main 是 NexusGate Go 网关的入口函数。
// 启动流程:
//  1. 解析命令行参数（可选 --env 指定 .env 文件路径）
//  2. 加载 .env 文件（指定路径 > 自动查找 .env.local > .env）
//  3. 加载配置（config.Load）
//  4. 初始化反向代理（proxy.Init）
//  5. 启动 WebSocket Hub（后台协程）
//  6. 创建限流器并设置路由
//  7. 启动 HTTP 服务并监听信号实现优雅关闭
func main() {
	// 解析命令行参数
	envFile := flag.String("env", "", "Path to .env file (auto-detect .env.local if empty)")
	flag.Parse()

	// 加载 .env 文件
	// 优先级: --env 指定路径 > 自动查找 .env.local > .env
	if *envFile != "" {
		// 用户显式指定了 .env 文件路径
		if err := loadEnvFile(*envFile); err != nil {
			log.Printf("Warning: failed to load .env file (%s): %v", *envFile, err)
		}
	} else {
		// 未指定 --env 时自动查找项目根目录的 .env.local / .env
		// 从当前工作目录向上逐级查找，最多上溯 5 级
		found := false
		for i := 0; i <= 5; i++ {
			dir := "."
			for j := 0; j < i; j++ {
				dir = filepath.Join(dir, "..")
			}

			// 优先查找 .env.local（本地开发环境）
			localPath := filepath.Join(dir, ".env.local")
			if _, err := os.Stat(localPath); err == nil {
				if err := loadEnvFile(localPath); err != nil {
					log.Printf("Warning: failed to load .env.local (%s): %v", localPath, err)
				} else {
					log.Printf("Loaded env file: %s", localPath)
					found = true
				}
				break
			}

			// 其次查找 .env（备用）
			envPath := filepath.Join(dir, ".env")
			if _, err := os.Stat(envPath); err == nil {
				if err := loadEnvFile(envPath); err != nil {
					log.Printf("Warning: failed to load .env (%s): %v", envPath, err)
				} else {
					log.Printf("Loaded env file: %s", envPath)
					found = true
				}
				break
			}
		}
		if !found {
			log.Printf("Warning: no .env.local or .env file found, using default config values")
			log.Printf("  Hint: specify with --env /path/to/.env.local or run from project root")
		}
	}

	// 日志文件输出 - 写入 NexusCockpit/logs/go_logs/ 文件夹
	// 支持从环境变量 LOG_DIR 覆盖，默认从当前工作目录向上查找项目根目录
	logDir := os.Getenv("LOG_DIR")
	if logDir == "" {
		// 从 backend_design/nexus_gate/ 运行，上溯 2 级到项目根目录
		logDir = filepath.Join("..", "..", "logs", "go_logs")
	}
	os.MkdirAll(logDir, os.ModePerm)
	logFile := filepath.Join(logDir, fmt.Sprintf("gateway_%s.log", time.Now().Format("20060102_150405")))
	file, err := os.OpenFile(logFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		log.Printf("Warning: failed to open log file: %v (will only log to console)", err)
	} else {
		defer file.Close()
		// 同时输出到控制台和文件
		log.SetOutput(io.MultiWriter(file, os.Stdout))
	}
	defer log.Println()

	// 加载配置
	cfg := config.Load()
	log.Printf("NexusGate starting...")
	log.Printf("  Gate: %s:%d", cfg.GateHost, cfg.GatePort)
	log.Printf("  AI Backend: %s", cfg.AIBaseURL())
	log.Printf("  Mode: %s", cfg.GateMode)
	log.Printf("  JWT Secret: %s", maskSecret(cfg.JWTSecret))
	log.Printf("  Log file: %s", logFile)

	// 初始化反向代理
	proxy.Init()

	// 创建 WebSocket Hub
	hub := ws.NewHub()
	go hub.Run()

	// 创建限流器（从配置读取 QPS 上限）
	limiter := ratelimit.NewRateLimiter(cfg.RateLimitQPS, cfg.RateLimitQPS)

	// 设置路由
	r := router.SetupRouter(hub, limiter)

	// 启动 HTTP 服务
	addr := fmt.Sprintf("%s:%d", cfg.GateHost, cfg.GatePort)
	log.Printf("NexusGate listening on %s", addr)

	// 优雅关闭
	go func() {
		if err := r.Run(addr); err != nil {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("NexusGate shutting down...")
	log.Println("NexusGate stopped")
}

// maskSecret 脱敏显示密钥，仅显示前 4 位和后 4 位，中间用 * 代替。
// 用于启动日志中打印 JWT 密钥，方便排查双端密钥不一致问题。
//
// 参数:
//   - s: 原始密钥字符串
//
// 返回值: 脱敏后的字符串（如 "nexu****2026"）
func maskSecret(s string) string {
	if len(s) <= 8 {
		return "****"
	}
	return s[:4] + "****" + s[len(s)-4:]
}

// loadEnvFile 加载 .env 文件到环境变量
func loadEnvFile(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}

	lines := string(data)
	for _, line := range strings.Split(lines, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || line[0] == '#' {
			continue
		}

		// KEY=VALUE
		idx := strings.IndexByte(line, '=')
		if idx < 0 {
			continue
		}

		key := strings.TrimSpace(line[:idx])
		val := strings.TrimSpace(line[idx+1:])

		// 去掉引号
		if len(val) >= 2 && (val[0] == '"' && val[len(val)-1] == '"') {
			val = val[1 : len(val)-1]
		}

		os.Setenv(key, val)
	}

	return nil
}
