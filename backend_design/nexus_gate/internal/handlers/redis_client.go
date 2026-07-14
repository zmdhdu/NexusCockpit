// Copyright (c) 2026 zhangmengdi (NexusCockpit)
// Licensed under the MIT License. See LICENSE in the project root for details.
// Source: https://github.com/zmdhdu/NexusCockpit

// 简易 Redis 客户端 — 使用 RESP 协议通过 TCP 直接通信
//
// 避免引入 go-redis 依赖，Demo 阶段够用。
// 支持: GET, SET, HGET, HGETALL, KEYS 等基本命令。
package handlers

import (
	"bufio"
	"fmt"
	"net"
	"strconv"
	"strings"
	"time"
)

// SimpleRedisClient 简易 Redis 客户端
type SimpleRedisClient struct {
	addr     string
	password string
	db       int
	conn     net.Conn
	reader   *bufio.Reader
}

// NewRedisClient 创建 Redis 客户端
func NewRedisClient(host string, port int, password string, db int) *SimpleRedisClient {
	addr := fmt.Sprintf("%s:%d", host, port)
	return &SimpleRedisClient{
		addr:     addr,
		password: password,
		db:       db,
	}
}

// Close 关闭连接
func (c *SimpleRedisClient) Close() {
	if c.conn != nil {
		c.conn.Close()
	}
}

// connect 建立连接
func (c *SimpleRedisClient) connect() error {
	conn, err := net.DialTimeout("tcp", c.addr, 3*time.Second)
	if err != nil {
		return err
	}
	c.conn = conn
	c.reader = bufio.NewReader(conn)

	// 认证
	if c.password != "" {
		if err := c.sendCommand("AUTH", c.password); err != nil {
			return err
		}
		resp, err := c.readReply()
		if err != nil || resp == nil {
			return fmt.Errorf("redis auth failed")
		}
	}

	// 选择 DB
	if c.db > 0 {
		if err := c.sendCommand("SELECT", strconv.Itoa(c.db)); err != nil {
			return err
		}
		_, err = c.readReply()
		if err != nil {
			return err
		}
	}

	return nil
}

// sendCommand 发送 RESP 格式命令
func (c *SimpleRedisClient) sendCommand(args ...string) error {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("*%d\r\n", len(args)))
	for _, arg := range args {
		sb.WriteString(fmt.Sprintf("$%d\r\n%s\r\n", len(arg), arg))
	}
	_, err := c.conn.Write([]byte(sb.String()))
	return err
}

// readReply 读取 RESP 响应
func (c *SimpleRedisClient) readReply() (interface{}, error) {
	line, err := c.reader.ReadString('\n')
	if err != nil {
		return nil, err
	}
	line = strings.TrimRight(line, "\r\n")

	if len(line) == 0 {
		return nil, fmt.Errorf("empty reply")
	}

	switch line[0] {
	case '+': // 简单字符串
		return line[1:], nil
	case '-': // 错误
		return nil, fmt.Errorf("redis error: %s", line[1:])
	case ':': // 整数
		val, err := strconv.ParseInt(line[1:], 10, 64)
		if err != nil {
			return nil, err
		}
		return val, nil
	case '$': // 批量字符串
		length, err := strconv.Atoi(line[1:])
		if err != nil {
			return nil, err
		}
		if length < 0 {
			return nil, nil // nil
		}
		data := make([]byte, length+2) // +2 for \r\n
		_, err = c.reader.Read(data)
		if err != nil {
			return nil, err
		}
		return string(data[:length]), nil
	case '*': // 数组
		count, err := strconv.Atoi(line[1:])
		if err != nil {
			return nil, err
		}
		if count < 0 {
			return nil, nil
		}
		result := make([]interface{}, count)
		for i := 0; i < count; i++ {
			result[i], err = c.readReply()
			if err != nil {
				return nil, err
			}
		}
		return result, nil
	default:
		return nil, fmt.Errorf("unknown reply type: %c", line[0])
	}
}

// Get 获取字符串值
func (c *SimpleRedisClient) Get(key string) (string, error) {
	if c.conn == nil {
		if err := c.connect(); err != nil {
			return "", err
		}
	}
	if err := c.sendCommand("GET", key); err != nil {
		return "", err
	}
	resp, err := c.readReply()
	if err != nil {
		return "", err
	}
	if resp == nil {
		return "", fmt.Errorf("key not found")
	}
	str, ok := resp.(string)
	if !ok {
		return "", fmt.Errorf("unexpected type")
	}
	return str, nil
}

// GetInt 获取整数值
func (c *SimpleRedisClient) GetInt(key string) (int, error) {
	val, err := c.Get(key)
	if err != nil {
		return 0, err
	}
	n, err := strconv.Atoi(val)
	if err != nil {
		return 0, err
	}
	return n, nil
}
