// Copyright (c) 2026 zhangmengdi (NexusCockpit)
// Licensed under the MIT License. See LICENSE in the project root for details.
// Source: https://github.com/zmdhdu/NexusCockpit

// Package ws — WebSocket Hub 管理千级连接
package ws

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"nexus_gate/internal/config"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true // Demo: 允许所有来源
	},
}

// Client WebSocket 客户端
type Client struct {
	conn       *websocket.Conn
	cockpitID  string
	userID     string
	send       chan []byte
	hub        *Hub
	backend    *websocket.Conn // 到 Python AI 的后端 WebSocket 连接
	token      string          // JWT Token（用于连接 Python WebSocket）
}

// Hub WebSocket 连接管理器
type Hub struct {
	clients    map[string]map[*Client]bool // cockpit_id → clients
	broadcast  chan *BroadcastMessage
	register   chan *Client
	unregister chan *Client
	mu         sync.RWMutex
}

// BroadcastMessage 广播消息
type BroadcastMessage struct {
	CockpitID string `json:"cockpit_id"`
	Type      string `json:"type"`
	Data      any    `json:"data"`
}

// NewHub 创建 Hub
func NewHub() *Hub {
	return &Hub{
		clients:    make(map[string]map[*Client]bool),
		broadcast:  make(chan *BroadcastMessage, 256),
		register:   make(chan *Client),
		unregister: make(chan *Client),
	}
}

// Run 启动 Hub
func (h *Hub) Run() {
	for {
		select {
		case client := <-h.register:
			h.mu.Lock()
			if h.clients[client.cockpitID] == nil {
				h.clients[client.cockpitID] = make(map[*Client]bool)
			}
			h.clients[client.cockpitID][client] = true
			h.mu.Unlock()
			log.Printf("WS client registered: cockpit=%s, user=%s", client.cockpitID, client.userID)

		case client := <-h.unregister:
			h.mu.Lock()
			if clients, ok := h.clients[client.cockpitID]; ok {
				if _, ok := clients[client]; ok {
					delete(clients, client)
					close(client.send)
				}
			}
			h.mu.Unlock()
			log.Printf("WS client unregistered: cockpit=%s, user=%s", client.cockpitID, client.userID)

		case msg := <-h.broadcast:
			h.mu.RLock()
			clients := h.clients[msg.CockpitID]
			h.mu.RUnlock()
			if clients != nil {
				data, _ := json.Marshal(msg)
				for client := range clients {
					select {
					case client.send <- data:
					default:
						// 发送缓冲区满，关闭连接
						h.mu.Lock()
						delete(clients, client)
						close(client.send)
						h.mu.Unlock()
					}
				}
			}
		}
	}
}

// BroadcastToCockpit 向指定座舱的所有客户端广播消息
func (h *Hub) BroadcastToCockpit(cockpitID, msgType string, data any) {
	h.broadcast <- &BroadcastMessage{
		CockpitID: cockpitID,
		Type:      msgType,
		Data:      data,
	}
}

// GetClientCount 获取指定座舱的连接数
func (h *Hub) GetClientCount(cockpitID string) int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients[cockpitID])
}

// GetAllClientCount 获取所有连接数
func (h *Hub) GetAllClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	count := 0
	for _, clients := range h.clients {
		count += len(clients)
	}
	return count
}

// HandleWebSocket 处理 WebSocket 连接
// W6: 将客户端消息转发到 Python AI WebSocket，并将 AI 响应回传给客户端
func (h *Hub) HandleWebSocket(w http.ResponseWriter, r *http.Request, cockpitID, userID string) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("WebSocket upgrade error: %v", err)
		return
	}

	// 从请求头提取 JWT Token（用于连接 Python WebSocket）
	token := ""
	if authHeader := r.Header.Get("Authorization"); len(authHeader) > 7 && authHeader[:7] == "Bearer " {
		token = authHeader[7:]
	}
	// 也检查 query 参数中的 token
	if token == "" {
		token = r.URL.Query().Get("token")
	}

	client := &Client{
		conn:      conn,
		cockpitID: cockpitID,
		userID:    userID,
		send:      make(chan []byte, 256),
		hub:       h,
		token:     token,
	}

	// 尝试连接到 Python AI WebSocket 后端
	client.connectBackend()

	h.register <- client

	go client.writePump()
	go client.readPump()

	// 如果后端连接成功，启动后端消息转发
	if client.backend != nil {
		go client.backendReadPump()
	}
}

// writePump 向客户端发送消息
func (c *Client) writePump() {
	defer c.conn.Close()

	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case message, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if !ok {
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			c.conn.WriteMessage(websocket.TextMessage, message)

		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

// connectBackend 连接到 Python AI WebSocket 后端
func (c *Client) connectBackend() {
	cfg := config.Get()
	aiHost := cfg.AIHost
	aiPort := cfg.AIPort

	// 构建 Python WebSocket URL
	// Python WebSocket 端点: /ws/chat?token=<jwt>
	wsURL := url.URL{
		Scheme:   "ws",
		Host:     fmt.Sprintf("%s:%d", aiHost, aiPort),
		Path:     "/ws/chat",
		RawQuery: "token=" + url.QueryEscape(c.token),
	}

	dialer := websocket.Dialer{
		HandshakeTimeout: 5 * time.Second,
	}

	backendConn, _, err := dialer.Dial(wsURL.String(), nil)
	if err != nil {
		log.Printf("WS backend connect failed for %s/%s: %v", c.cockpitID, c.userID, err)
		return
	}

	c.backend = backendConn
	log.Printf("WS backend connected for %s/%s", c.cockpitID, c.userID)
}

// backendReadPump 从 Python AI 后端读取消息并转发给客户端
func (c *Client) backendReadPump() {
	defer func() {
		if c.backend != nil {
			c.backend.Close()
			c.backend = nil
		}
	}()

	for {
		_, message, err := c.backend.ReadMessage()
		if err != nil {
			log.Printf("WS backend read error for %s/%s: %v", c.cockpitID, c.userID, err)
			break
		}
		// 将 AI 响应转发给客户端
		select {
		case c.send <- message:
		default:
			// 发送缓冲区满，关闭连接
			log.Printf("WS send buffer full for %s/%s, closing", c.cockpitID, c.userID)
			return
		}
	}
}

// readPump 读取客户端消息
func (c *Client) readPump() {
	defer func() {
		c.hub.unregister <- c
		c.conn.Close()
		if c.backend != nil {
			c.backend.Close()
		}
	}()

	c.conn.SetReadLimit(65536) // 64KB，支持较大的语音数据
	c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		_, message, err := c.conn.ReadMessage()
		if err != nil {
			break
		}

		// W6: 转发消息到 Python AI WebSocket 后端
		if c.backend != nil {
			// 在消息中注入 cockpit_id 和 user_id（如果不存在）
			enhancedMsg := injectCockpitInfo(message, c.cockpitID, c.userID)
			c.backend.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := c.backend.WriteMessage(websocket.TextMessage, enhancedMsg); err != nil {
				log.Printf("WS backend write error for %s/%s: %v", c.cockpitID, c.userID, err)
				// 后端断开，尝试重连
				c.connectBackend()
				if c.backend != nil {
					c.backend.WriteMessage(websocket.TextMessage, enhancedMsg)
				}
			}
		} else {
			// 后端不可用，返回错误提示
			errMsg, _ := json.Marshal(map[string]interface{}{
				"type": "error",
				"data": map[string]interface{}{
					"message": "AI service unavailable. Please try again later.",
				},
			})
			select {
			case c.send <- errMsg:
			default:
			}
		}
	}
}

// injectCockpitInfo 在 WebSocket 消息中注入 cockpit_id 和 user_id
func injectCockpitInfo(message []byte, cockpitID, userID string) []byte {
	var data map[string]interface{}
	if err := json.Unmarshal(message, &data); err != nil {
		// 非 JSON 消息，包装后转发
		data = map[string]interface{}{
			"text":    string(message),
			"cockpit_id": cockpitID,
			"user_id":    userID,
		}
		result, _ := json.Marshal(data)
		return result
	}

	// 注入 cockpit_id 和 user_id（如果不存在）
	if _, exists := data["cockpit_id"]; !exists {
		data["cockpit_id"] = cockpitID
	}
	if _, exists := data["user_id"]; !exists {
		data["user_id"] = userID
	}

	result, _ := json.Marshal(data)
	return result
}
