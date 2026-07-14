# Dockerfile for NexusGate (Go Gateway) — v2.1
# 多阶段构建：builder 编译 Go 二进制，runner 运行
FROM golang:1.22-alpine AS builder

WORKDIR /app

# 先复制 go.mod，利用 Docker 缓存加速
COPY go.mod ./
RUN go mod download || true

# 复制源码并编译
COPY . .
RUN go mod tidy && CGO_ENABLED=0 GOOS=linux go build -o /nexus_gate ./cmd/

# 运行阶段：最小化镜像
FROM alpine:3.19
RUN apk --no-cache add ca-certificates wget
COPY --from=builder /nexus_gate /nexus_gate

EXPOSE 8080
CMD ["/nexus_gate"]
