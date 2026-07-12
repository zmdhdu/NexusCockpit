// Package ratelimit — 优先级令牌桶限流
//
// 支持三级优先级:
//   - PriorityHigh:   车控指令、ASR/TTS 等实时性要求高的请求
//   - PriorityNormal: 对话请求（默认）
//   - PriorityLow:    状态查询、数据中台等非实时请求
//
// 限流策略:
//   - 每个座舱有独立令牌桶
//   - 令牌总数 = capacity
//   - 高优先级可使用全部令牌
//   - 普通优先级最多使用 80% 令牌
//   - 低优先级最多使用 50% 令牌
//   - 全局限流 = 座舱限流 × 3
package ratelimit

import (
	"sync"
	"time"
)

// Priority 请求优先级
type Priority int

const (
	PriorityLow    Priority = 1 // 状态查询、数据中台
	PriorityNormal Priority = 2 // 对话请求（默认）
	PriorityHigh   Priority = 3 // 车控指令、ASR/TTS
)

// priorityThreshold 各优先级可用的令牌比例（相对于 capacity）
var priorityThreshold = map[Priority]float64{
	PriorityLow:    0.50, // 低优先级最多用 50% 令牌
	PriorityNormal: 0.80, // 普通优先级最多用 80% 令牌
	PriorityHigh:   1.00, // 高优先级可用全部令牌
}

// TokenBucket 令牌桶
type TokenBucket struct {
	mu         sync.Mutex
	capacity   int           // 桶容量
	tokens     int           // 当前令牌数
	rate       time.Duration // 令牌生成间隔
	lastRefill time.Time
}

// NewTokenBucket 创建令牌桶
func NewTokenBucket(capacity int, ratePerSecond int) *TokenBucket {
	return &TokenBucket{
		capacity:   capacity,
		tokens:     capacity,
		rate:       time.Second / time.Duration(ratePerSecond),
		lastRefill: time.Now(),
	}
}

// refill 补充令牌（调用前需持有锁）
func (tb *TokenBucket) refill() {
	now := time.Now()
	elapsed := now.Sub(tb.lastRefill)
	refill := int(elapsed / tb.rate)
	if refill > 0 {
		tb.tokens += refill
		if tb.tokens > tb.capacity {
			tb.tokens = tb.capacity
		}
		tb.lastRefill = now
	}
}

// Allow 尝试获取一个令牌（普通优先级）
func (tb *TokenBucket) Allow() bool {
	return tb.AllowWithPriority(PriorityNormal)
}

// AllowWithPriority 按优先级尝试获取令牌
func (tb *TokenBucket) AllowWithPriority(p Priority) bool {
	tb.mu.Lock()
	defer tb.mu.Unlock()

	tb.refill()

	// 检查该优先级是否有权使用当前剩余令牌
	threshold := int(float64(tb.capacity) * priorityThreshold[p])
	// 已用令牌数 = 容量 - 剩余令牌
	used := tb.capacity - tb.tokens
	if used >= threshold {
		// 该优先级已用完配额
		return false
	}

	if tb.tokens > 0 {
		tb.tokens--
		return true
	}
	return false
}

// AvailableTokens 返回当前可用令牌数（用于监控）
func (tb *TokenBucket) AvailableTokens() int {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	tb.refill()
	return tb.tokens
}

// RateLimiter 座舱级优先级限流器
type RateLimiter struct {
	buckets      map[string]*TokenBucket // cockpit_id → bucket
	globalBucket *TokenBucket            // 全局限流
	mu           sync.RWMutex
	capacity     int
	rate         int
}

// NewRateLimiter 创建限流器
func NewRateLimiter(capacity, ratePerSecond int) *RateLimiter {
	return &RateLimiter{
		buckets:      make(map[string]*TokenBucket),
		globalBucket: NewTokenBucket(capacity*3, ratePerSecond*3), // 全局上限 = 座舱上限 × 3
		capacity:     capacity,
		rate:         ratePerSecond,
	}
}

// Allow 检查指定座舱是否允许通过（普通优先级）
func (rl *RateLimiter) Allow(cockpitID string) bool {
	return rl.AllowWithPriority(cockpitID, PriorityNormal)
}

// AllowWithPriority 按优先级检查指定座舱是否允许通过
func (rl *RateLimiter) AllowWithPriority(cockpitID string, p Priority) bool {
	// 先检查全局桶
	if !rl.globalBucket.AllowWithPriority(p) {
		return false
	}

	rl.mu.RLock()
	bucket, exists := rl.buckets[cockpitID]
	rl.mu.RUnlock()

	if !exists {
		rl.mu.Lock()
		bucket, exists = rl.buckets[cockpitID]
		if !exists {
			bucket = NewTokenBucket(rl.capacity, rl.rate)
			rl.buckets[cockpitID] = bucket
		}
		rl.mu.Unlock()
	}

	return bucket.AllowWithPriority(p)
}

// GetStats 获取限流器统计信息（用于数据中台）
func (rl *RateLimiter) GetStats() map[string]interface{} {
	rl.mu.RLock()
	defer rl.mu.RUnlock()

	cockpitStats := make(map[string]interface{})
	for cid, bucket := range rl.buckets {
		cockpitStats[cid] = map[string]interface{}{
			"available_tokens": bucket.AvailableTokens(),
			"capacity":         rl.capacity,
		}
	}

	return map[string]interface{}{
		"global_available": rl.globalBucket.AvailableTokens(),
		"global_capacity":  rl.capacity * 3,
		"cockpits":         cockpitStats,
	}
}
