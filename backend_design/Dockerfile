# Dockerfile for NexusCockpit Python AI Backend — v2.1
# 多阶段构建：builder 安装依赖，runner 运行 FastAPI
FROM python:3.11-slim AS builder

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================
# 运行阶段
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# 从 builder 复制已安装的 Python 包
COPY --from=builder /root/.local /root/.local

# 复制项目代码
COPY . .

# 确保 Python 能找到用户安装的包
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["python", "-m", "uvicorn", "nexus.main:app", "--host", "0.0.0.0", "--port", "8000"]
