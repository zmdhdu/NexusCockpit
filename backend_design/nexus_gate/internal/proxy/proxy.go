// Copyright (c) 2026 zhangmengdi (NexusCockpit)
// Licensed under the MIT License. See LICENSE in the project root for details.
// Source: https://github.com/zmdhdu/NexusCockpit

// Package proxy — 反向代理到 Python AI 服务
//
// 职责:
// 1. 将 Go 网关收到的请求转发到 Python FastAPI
// 2. 在请求头中注入 X-Cockpit-Id / X-User-Id / X-User-Role 供 Python 端识别租户
// 3. 统一处理 AI 服务不可用时的错误响应
package proxy

import (
	"context"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"

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
		// 传递客户端真实 IP，供后端 IP 定位使用
		// Go 标准库的 ReverseProxy 不会自动设置 X-Forwarded-For，
		// 需要手动从 RemoteAddr 提取并设置
		if req.RemoteAddr != "" {
			// RemoteAddr 格式为 "host:port"，提取 host 部分
			clientHost := req.RemoteAddr
			if idx := strings.LastIndex(clientHost, ":"); idx != -1 {
				clientHost = clientHost[:idx]
			}
			// 如果已有 X-Forwarded-For（多层代理），追加到末尾
			existing := req.Header.Get("X-Forwarded-For")
			if existing != "" {
				req.Header.Set("X-Forwarded-For", existing+", "+clientHost)
			} else {
				req.Header.Set("X-Forwarded-For", clientHost)
			}
		}
	}

	// 自定义 ModifyResponse: 可在此修改上游响应（如添加头信息）
	ReverseProxy.ModifyResponse = func(resp *http.Response) error {
		resp.Header.Set("X-Served-By", "nexus_gate")

		// 剥离上游 (Python FastAPI CORSMiddleware) 返回的 CORS 响应头。
		// 原因: Go 网关的 CORS 中间件已经设置了这些头，反向代理的 copyHeader
		// 会用 Header.Add() 追加上游的头，导致浏览器收到重复值
		// (如 "Access-Control-Allow-Origin: *, *") 从而拒绝请求。
		// 在此删除上游的 CORS 头，确保只有网关一层控制 CORS。
		resp.Header.Del("Access-Control-Allow-Origin")
		resp.Header.Del("Access-Control-Allow-Methods")
		resp.Header.Del("Access-Control-Allow-Headers")
		resp.Header.Del("Access-Control-Allow-Credentials")
		resp.Header.Del("Access-Control-Max-Age")
		resp.Header.Del("Access-Control-Expose-Headers")
		resp.Header.Del("Vary")

		return nil
	}

	// 自定义错误处理: AI 服务不可用时返回 502；客户端断开时静默关闭
	ReverseProxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		// 客户端主动断开连接（切换座舱时 abort 请求）— 不写响应，静默处理
		if err == context.Canceled || strings.Contains(err.Error(), "forcibly closed") {
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		w.Write([]byte(`{"error": "AI_SERVICE_UNAVAILABLE", "message": "Python AI service is unavailable"}`))
	}
}
