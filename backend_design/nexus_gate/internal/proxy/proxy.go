// Package proxy — 反向代理到 Python AI 服务
//
// 职责:
// 1. 将 Go 网关收到的请求转发到 Python FastAPI
// 2. 在请求头中注入 X-Cockpit-Id / X-User-Id / X-User-Role 供 Python 端识别租户
// 3. 统一处理 AI 服务不可用时的错误响应
package proxy

import (
	"net/http"
	"net/http/httputil"
	"net/url"

	"nexus_gate/internal/config"
)

// ReverseProxy 反向代理到 Python FastAPI
var ReverseProxy *httputil.ReverseProxy

// Init 初始化反向代理
func Init() {
	cfg := config.Get()
	target, _ := url.Parse(cfg.AIBaseURL())

	ReverseProxy = httputil.NewSingleHostReverseProxy(target)

	// 自定义 Director: 设置转发头信息
	originalDirector := ReverseProxy.Director
	ReverseProxy.Director = func(req *http.Request) {
		originalDirector(req)
		// 标记请求来源
		req.Header.Set("X-Forwarded-By", "nexus_gate")
		req.Header.Set("X-Forwarded-Host", req.Host)
	}

	// 自定义 ModifyResponse: 可在此修改上游响应（如添加头信息）
	ReverseProxy.ModifyResponse = func(resp *http.Response) error {
		resp.Header.Set("X-Served-By", "nexus_gate")
		return nil
	}

	// 自定义错误处理: AI 服务不可用时返回 502
	ReverseProxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		w.Write([]byte(`{"error": "AI_SERVICE_UNAVAILABLE", "message": "Python AI service is unavailable"}`))
	}
}
