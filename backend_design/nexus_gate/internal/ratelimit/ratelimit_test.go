package ratelimit

import (
	"sync"
	"testing"
	"time"
)

func TestTokenBucketAllowHighPriority(t *testing.T) {
	// 创建容量 5、每秒 5 令牌的桶
	bucket := NewTokenBucket(5, 5)

	// 高优先级可使用全部令牌，前 5 次应全部通过
	for i := 0; i < 5; i++ {
		if !bucket.AllowWithPriority(PriorityHigh) {
			t.Fatalf("High priority request %d should be allowed", i)
		}
	}

	// 第 6 次应被拒绝（令牌耗尽）
	if bucket.AllowWithPriority(PriorityHigh) {
		t.Fatal("6th high priority request should be rate limited")
	}
}

func TestTokenBucketAllowNormalPriority(t *testing.T) {
	// 创建容量 10、每秒 100 令牌的桶
	bucket := NewTokenBucket(10, 100)

	// 普通优先级最多使用 80% = 8 个令牌
	allowed := 0
	for i := 0; i < 10; i++ {
		if bucket.AllowWithPriority(PriorityNormal) {
			allowed++
		}
	}

	if allowed != 8 {
		t.Fatalf("Normal priority should allow 8 requests, got %d", allowed)
	}
}

func TestTokenBucketAllowLowPriority(t *testing.T) {
	// 创建容量 10、每秒 100 令牌的桶
	bucket := NewTokenBucket(10, 100)

	// 低优先级最多使用 50% = 5 个令牌
	allowed := 0
	for i := 0; i < 10; i++ {
		if bucket.AllowWithPriority(PriorityLow) {
			allowed++
		}
	}

	if allowed != 5 {
		t.Fatalf("Low priority should allow 5 requests, got %d", allowed)
	}
}

func TestTokenBucketRefill(t *testing.T) {
	bucket := NewTokenBucket(2, 10) // 容量 2, 10 QPS

	// 耗尽令牌（使用高优先级以使用全部令牌）
	bucket.AllowWithPriority(PriorityHigh)
	bucket.AllowWithPriority(PriorityHigh)
	if bucket.AllowWithPriority(PriorityHigh) {
		t.Fatal("3rd request should be rate limited")
	}

	// 等待令牌补充（10 QPS = 100ms/令牌）
	time.Sleep(150 * time.Millisecond)

	// 应该有 1 个新令牌
	if !bucket.AllowWithPriority(PriorityHigh) {
		t.Fatal("Request after refill should be allowed")
	}
}

func TestRateLimiterPerCockpit(t *testing.T) {
	limiter := NewRateLimiter(3, 100) // 每座舱 3 QPS

	// cockpit-01 的前 3 个请求应通过（高优先级可用全部）
	for i := 0; i < 3; i++ {
		if !limiter.AllowWithPriority("cockpit-01", PriorityHigh) {
			t.Fatalf("cockpit-01 request %d should be allowed", i)
		}
	}

	// cockpit-01 的第 4 个请求应被拒绝
	if limiter.AllowWithPriority("cockpit-01", PriorityHigh) {
		t.Fatal("cockpit-01 4th request should be rate limited")
	}

	// cockpit-02 应不受影响（独立限流）
	for i := 0; i < 3; i++ {
		if !limiter.AllowWithPriority("cockpit-02", PriorityHigh) {
			t.Fatalf("cockpit-02 request %d should be allowed", i)
		}
	}
}

func TestRateLimiterConcurrency(t *testing.T) {
	limiter := NewRateLimiter(10, 100)
	var allowed, denied int
	var mu sync.Mutex

	var wg sync.WaitGroup
	// 20 个并发请求（高优先级）
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ok := limiter.AllowWithPriority("cockpit-concurrent", PriorityHigh)
			mu.Lock()
			if ok {
				allowed++
			} else {
				denied++
			}
			mu.Unlock()
		}()
	}
	wg.Wait()

	// 总数应为 20
	if allowed+denied != 20 {
		t.Errorf("Expected total 20, got %d (allowed=%d, denied=%d)", allowed+denied, allowed, denied)
	}

	// 允许的请求数不应超过全局限流上限
	// 全局桶 = 10*3 = 30，座舱桶 = 10，所以最多 10 个通过
	if allowed > 10 {
		t.Errorf("Expected at most 10 allowed, got %d", allowed)
	}
}

func TestPriorityPreemption(t *testing.T) {
	// 验证高优先级可以在低优先级耗尽配额后继续使用
	bucket := NewTokenBucket(10, 100)

	// 低优先级先用掉 5 个（50%）
	for i := 0; i < 5; i++ {
		if !bucket.AllowWithPriority(PriorityLow) {
			t.Fatalf("Low priority request %d should be allowed", i)
		}
	}

	// 低优先级第 6 个应被拒绝
	if bucket.AllowWithPriority(PriorityLow) {
		t.Fatal("6th low priority request should be denied")
	}

	// 高优先级仍然可以使用剩余令牌
	for i := 0; i < 5; i++ {
		if !bucket.AllowWithPriority(PriorityHigh) {
			t.Fatalf("High priority request %d should be allowed after low priority exhausted", i)
		}
	}

	// 全部耗尽
	if bucket.AllowWithPriority(PriorityHigh) {
		t.Fatal("High priority request should be denied when all tokens exhausted")
	}
}
