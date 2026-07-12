package config

import (
	"os"
	"testing"
)

func TestLoadDefaults(t *testing.T) {
	// 测试默认值加载
	cfg := Load()

	if cfg.GateHost != "0.0.0.0" {
		t.Errorf("Expected default GateHost '0.0.0.0', got '%s'", cfg.GateHost)
	}
	if cfg.GatePort != 8080 {
		t.Errorf("Expected default GatePort 8080, got %d", cfg.GatePort)
	}
	if cfg.AIHost != "127.0.0.1" {
		t.Errorf("Expected default AIHost '127.0.0.1', got '%s'", cfg.AIHost)
	}
	if cfg.AIPort != 8000 {
		t.Errorf("Expected default AIPort 8000, got %d", cfg.AIPort)
	}
	if cfg.GateMode != "proxy" {
		t.Errorf("Expected default GateMode 'proxy', got '%s'", cfg.GateMode)
	}
	if cfg.CockpitCount != 3 {
		t.Errorf("Expected default CockpitCount 3, got %d", cfg.CockpitCount)
	}
	if cfg.IsolationMode != "shared" {
		t.Errorf("Expected default IsolationMode 'shared', got '%s'", cfg.IsolationMode)
	}
}

func TestLoadFromEnv(t *testing.T) {
	// 设置环境变量
	os.Setenv("NEXUS_GATE_PORT", "9090")
	os.Setenv("NEXUS_AI_HOST", "10.0.0.1")
	os.Setenv("NEXUS_AI_PORT", "9999")
	os.Setenv("COCKPIT_COUNT", "5")
	os.Setenv("JWT_SECRET", "test-secret")
	defer func() {
		os.Unsetenv("NEXUS_GATE_PORT")
		os.Unsetenv("NEXUS_AI_HOST")
		os.Unsetenv("NEXUS_AI_PORT")
		os.Unsetenv("COCKPIT_COUNT")
		os.Unsetenv("JWT_SECRET")
	}()

	cfg := Load()

	if cfg.GatePort != 9090 {
		t.Errorf("Expected GatePort 9090, got %d", cfg.GatePort)
	}
	if cfg.AIHost != "10.0.0.1" {
		t.Errorf("Expected AIHost '10.0.0.1', got '%s'", cfg.AIHost)
	}
	if cfg.AIPort != 9999 {
		t.Errorf("Expected AIPort 9999, got %d", cfg.AIPort)
	}
	if cfg.CockpitCount != 5 {
		t.Errorf("Expected CockpitCount 5, got %d", cfg.CockpitCount)
	}
	if cfg.JWTSecret != "test-secret" {
		t.Errorf("Expected JWTSecret 'test-secret', got '%s'", cfg.JWTSecret)
	}
}

func TestAIBaseURL(t *testing.T) {
	cfg := &Config{
		AIHost: "192.168.1.100",
		AIPort: 8000,
	}
	expected := "http://192.168.1.100:8000"
	if cfg.AIBaseURL() != expected {
		t.Errorf("Expected AIBaseURL '%s', got '%s'", expected, cfg.AIBaseURL())
	}
}

func TestGetGlobalConfig(t *testing.T) {
	// Get() 应返回已加载的配置
	cfg1 := Load()
	cfg2 := Get()
	if cfg1 != cfg2 {
		t.Error("Get() should return the same config instance as Load()")
	}
}
