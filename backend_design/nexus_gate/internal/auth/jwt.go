// Package auth — JWT 签发与验证 + RBAC 权限校验
package auth

import (
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"

	"nexus_gate/internal/config"
)

// Claims JWT 载荷
type Claims struct {
	UserID    string `json:"user_id"`
	CockpitID string `json:"cockpit_id"`
	Role      string `json:"role"`
	Username  string `json:"username"`
	jwt.RegisteredClaims
}

// GenerateToken 签发 JWT Token
func GenerateToken(userID, cockpitID, role, username string) (string, error) {
	cfg := config.Get()
	expireHours := time.Duration(cfg.JWTExpireHours) * time.Hour

	claims := &Claims{
		UserID:    userID,
		CockpitID: cockpitID,
		Role:      role,
		Username:  username,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(expireHours)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			Issuer:    "nexus_gate",
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(cfg.JWTSecret))
}

// ParseToken 解析 JWT Token
func ParseToken(tokenString string) (*Claims, error) {
	cfg := config.Get()

	// 去掉 Bearer 前缀
	tokenString = strings.TrimPrefix(tokenString, "Bearer ")
	tokenString = strings.TrimSpace(tokenString)

	token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return []byte(cfg.JWTSecret), nil
	})

	if err != nil {
		return nil, err
	}

	if claims, ok := token.Claims.(*Claims); ok && token.Valid {
		return claims, nil
	}

	return nil, errors.New("invalid token")
}

// ValidateCockpitAccess 校验用户是否有权访问指定座舱
// super_admin 可以访问所有座舱，其他角色只能访问绑定的座舱
func ValidateCockpitAccess(claims *Claims, cockpitID string) error {
	if claims.Role == "super_admin" {
		return nil
	}
	if claims.CockpitID != cockpitID {
		return fmt.Errorf("access denied: user %s cannot access cockpit %s", claims.UserID, cockpitID)
	}
	return nil
}

// CheckPermission 检查角色是否拥有指定权限
func CheckPermission(role, permission string) bool {
	permissions := rolePermissions(role)
	for _, p := range permissions {
		if p == permission {
			return true
		}
	}
	return false
}

// rolePermissions 返回角色的权限列表
func rolePermissions(role string) []string {
	switch role {
	case "super_admin":
		return []string{
			"cockpit:register", "cockpit:delete", "cockpit:update",
			"cockpit:chat", "cockpit:vehicle",
			"dataplatform:view", "middleware:view",
			"settings:manage", "user:manage",
		}
	case "cockpit_admin":
		return []string{
			"cockpit:update", "cockpit:chat", "cockpit:vehicle",
			"dataplatform:view", "user:manage",
		}
	case "cockpit_user":
		return []string{
			"cockpit:chat", "cockpit:vehicle",
		}
	case "cockpit_viewer":
		return []string{
			"cockpit:view",
		}
	default:
		return []string{}
	}
}
