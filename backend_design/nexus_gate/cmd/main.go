// NexusGate — NexusCockpit v2.1 Go 并发网关
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
	"log"
	"os"
	"os/signal"
	"syscall"

	"nexus_gate/internal/config"
	"nexus_gate/internal/proxy"
	"nexus_gate/internal/ratelimit"
	"nexus_gate/internal/router"
	"nexus_gate/internal/ws"
)

func main() {
	// 解析命令行参数
	envFile := flag.String("env", "", "Path to .env file")
	flag.Parse()

	// 加载 .env 文件（如果指定）
	if *envFile != "" {
		if err := loadEnvFile(*envFile); err != nil {
			log.Printf("Warning: failed to load .env file: %v", err)
		}
	}

	// 加载配置
	cfg := config.Load()
	log.Printf("NexusGate v2.1 starting...")
	log.Printf("  Gate: %s:%d", cfg.GateHost, cfg.GatePort)
	log.Printf("  AI Backend: %s", cfg.AIBaseURL())
	log.Printf("  Mode: %s", cfg.GateMode)

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

// loadEnvFile 加载 .env 文件到环境变量
func loadEnvFile(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}

	lines := string(data)
	for _, line := range splitLines(lines) {
		line = trimSpace(line)
		if line == "" || line[0] == '#' {
			continue
		}

		// KEY=VALUE
		idx := indexOf(line, '=')
		if idx < 0 {
			continue
		}

		key := trimSpace(line[:idx])
		val := trimSpace(line[idx+1:])

		// 去掉引号
		if len(val) >= 2 && (val[0] == '"' && val[len(val)-1] == '"') {
			val = val[1 : len(val)-1]
		}

		os.Setenv(key, val)
	}

	return nil
}

func splitLines(s string) []string {
	var lines []string
	start := 0
	for i, c := range s {
		if c == '\n' {
			lines = append(lines, s[start:i])
			start = i + 1
		}
	}
	if start < len(s) {
		lines = append(lines, s[start:])
	}
	return lines
}

func trimSpace(s string) string {
	start := 0
	end := len(s)
	for start < end && (s[start] == ' ' || s[start] == '\t' || s[start] == '\r') {
		start++
	}
	for end > start && (s[end-1] == ' ' || s[end-1] == '\t' || s[end-1] == '\r') {
		end--
	}
	return s[start:end]
}

func indexOf(s string, c byte) int {
	for i := 0; i < len(s); i++ {
		if s[i] == c {
			return i
		}
	}
	return -1
}
