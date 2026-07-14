// Copyright (c) 2026 zhangmengdi (NexusCockpit)
// Licensed under the MIT License. See LICENSE in the project root for details.
// Source: https://github.com/zmdhdu/NexusCockpit

package auth

import (
	"testing"

	"nexus_gate/internal/config"
)

func init() {
	// 初始化测试配置
	config.Load()
}

func TestGenerateAndParseToken(t *testing.T) {
	// 生成 Token
	token, err := GenerateToken("user_01", "cockpit-01", "cockpit_user", "testuser")
	if err != nil {
		t.Fatalf("GenerateToken failed: %v", err)
	}
	if token == "" {
		t.Fatal("Token should not be empty")
	}

	// 解析 Token
	claims, err := ParseToken(token)
	if err != nil {
		t.Fatalf("ParseToken failed: %v", err)
	}
	if claims.UserID != "user_01" {
		t.Errorf("Expected UserID 'user_01', got '%s'", claims.UserID)
	}
	if claims.CockpitID != "cockpit-01" {
		t.Errorf("Expected CockpitID 'cockpit-01', got '%s'", claims.CockpitID)
	}
	if claims.Role != "cockpit_user" {
		t.Errorf("Expected Role 'cockpit_user', got '%s'", claims.Role)
	}
	if claims.Username != "testuser" {
		t.Errorf("Expected Username 'testuser', got '%s'", claims.Username)
	}
}

func TestParseTokenWithBearerPrefix(t *testing.T) {
	token, _ := GenerateToken("user_02", "cockpit-02", "cockpit_admin", "admin_user")

	// 带 Bearer 前缀解析
	claims, err := ParseToken("Bearer " + token)
	if err != nil {
		t.Fatalf("ParseToken with Bearer prefix failed: %v", err)
	}
	if claims.UserID != "user_02" {
		t.Errorf("Expected UserID 'user_02', got '%s'", claims.UserID)
	}
}

func TestParseInvalidToken(t *testing.T) {
	// 无效 Token
	_, err := ParseToken("invalid.token.here")
	if err == nil {
		t.Fatal("Expected error for invalid token")
	}

	// 空 Token
	_, err = ParseToken("")
	if err == nil {
		t.Fatal("Expected error for empty token")
	}
}

func TestValidateCockpitAccess(t *testing.T) {
	// 普通用户只能访问绑定的座舱
	claims := &Claims{
		UserID:    "user_01",
		CockpitID: "cockpit-01",
		Role:      "cockpit_user",
	}

	// 访问自己的座舱 — 应通过
	err := ValidateCockpitAccess(claims, "cockpit-01")
	if err != nil {
		t.Errorf("Expected access to own cockpit, got error: %v", err)
	}

	// 访问其他座舱 — 应拒绝
	err = ValidateCockpitAccess(claims, "cockpit-02")
	if err == nil {
		t.Fatal("Expected access denied for other cockpit")
	}

	// super_admin 可访问所有座舱
	adminClaims := &Claims{
		UserID:    "admin",
		CockpitID: "",
		Role:      "super_admin",
	}
	err = ValidateCockpitAccess(adminClaims, "cockpit-01")
	if err != nil {
		t.Errorf("Expected super_admin to access any cockpit, got error: %v", err)
	}
	err = ValidateCockpitAccess(adminClaims, "cockpit-99")
	if err != nil {
		t.Errorf("Expected super_admin to access any cockpit, got error: %v", err)
	}
}

func TestCheckPermission(t *testing.T) {
	// super_admin 应有所有权限
	if !CheckPermission("super_admin", "cockpit:register") {
		t.Error("super_admin should have cockpit:register permission")
	}
	if !CheckPermission("super_admin", "settings:manage") {
		t.Error("super_admin should have settings:manage permission")
	}

	// cockpit_admin 权限
	if !CheckPermission("cockpit_admin", "cockpit:chat") {
		t.Error("cockpit_admin should have cockpit:chat permission")
	}
	if CheckPermission("cockpit_admin", "cockpit:register") {
		t.Error("cockpit_admin should NOT have cockpit:register permission")
	}

	// cockpit_user 权限
	if !CheckPermission("cockpit_user", "cockpit:chat") {
		t.Error("cockpit_user should have cockpit:chat permission")
	}
	if CheckPermission("cockpit_user", "settings:manage") {
		t.Error("cockpit_user should NOT have settings:manage permission")
	}

	// cockpit_viewer 权限
	if !CheckPermission("cockpit_viewer", "cockpit:view") {
		t.Error("cockpit_viewer should have cockpit:view permission")
	}
	if CheckPermission("cockpit_viewer", "cockpit:chat") {
		t.Error("cockpit_viewer should NOT have cockpit:chat permission")
	}

	// 未知角色
	if CheckPermission("unknown_role", "any:permission") {
		t.Error("Unknown role should have no permissions")
	}
}
