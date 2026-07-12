# Dockerfile for NexusCockpit Frontend (Next.js) — v2.1
# 多阶段构建：builder 编译 Next.js，runner 运行
FROM node:18-alpine AS builder

WORKDIR /app

# 复制 package.json 并安装依赖（利用 Docker 缓存）
COPY package.json package-lock.json* ./
RUN npm ci || npm install

# 复制源码并构建
COPY . .
RUN npm run build

# ============================================================
# 运行阶段
# ============================================================
FROM node:18-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# 从 builder 复制构建产物
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
