# ============================================================
# NexusCockpit Python AI Backend — v2.2 多阶段构建
# P4 优化: CPU-only PyTorch + python:3.10-slim + 分层缓存
# ============================================================

# ---- Stage 1: Builder (安装依赖) ----
FROM python:3.10-slim AS builder

WORKDIR /app

# 系统依赖 (编译所需)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git && \
    rm -rf /var/lib/apt/lists/*

# 先安装 CPU-only PyTorch (大幅减小镜像体积，~2GB → ~200MB)
# requirements.txt 注释中要求 PyTorch 单独安装
RUN pip install --no-cache-dir --user \
    torch==2.5.1 torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/cpu

# 再安装其余 Python 依赖 (利用 Docker 层缓存)
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================
# ---- Stage 2: Runner (运行环境) ----
# ============================================================
FROM python:3.10-slim

WORKDIR /app

# 运行时系统依赖 (curl for healthcheck, libsndfile for audio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的 Python 包 (含 CPU-only PyTorch)
COPY --from=builder /root/.local /root/.local

# 复制项目代码 (利用 .dockerignore 排除 models/data/logs)
COPY . .

# 环境变量
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=30s \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["python", "-m", "uvicorn", "nexus.main:app", "--host", "0.0.0.0", "--port", "8000"]
