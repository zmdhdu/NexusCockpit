# ============================================================
# NexusCockpit Makefile
# Usage: make <target>
#
# 项目结构:
#   NexusCockpit/
#   ├── backend_design/  # 后端 Python 代码
#   │   └── nexus_gate/  # Go API 网关
#   ├── frontend_design/ # 前端 Next.js 代码
#   ├── docs/            # 文档
#   ├── models/          # 模型文件
#   ├── data/            # 数据文件
#   ├── assets/          # 音频资源
#   ├── config/          # Docker/Grafana/Prometheus 配置
#   ├── .env             # 环境变量 (前后端共享)
#   └── Makefile         # 本文件
# ============================================================

.PHONY: help install install-gpu install-frontend install-gateway dev dev-frontend dev-all dev-log dev-frontend-log dev-gateway-log test lint format check clean docker-up docker-down docker-logs docker-clean init-db lint-backend lint-gateway build-gateway

PYTHON := python
PIP := pip
VENV := .venv

# 目录常量
BACKEND_DIR := backend_design
FRONTEND_DIR := frontend_design
GATEWAY_DIR := backend_design/nexus_gate

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================
# Environment Setup
# ============================================================

install: ## Create virtual environment and install backend dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV)/Scripts/activate && $(PIP) install --upgrade pip setuptools wheel
	$(VENV)/Scripts/activate && $(PIP) install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
	$(VENV)/Scripts/activate && $(PIP) install -r $(BACKEND_DIR)/requirements.txt
	@echo "✓ Backend environment ready. Activate with: $(VENV)\\Scripts\\activate"

install-gpu: ## Create virtual environment with GPU PyTorch
	$(PYTHON) -m venv $(VENV)
	$(VENV)/Scripts/activate && $(PIP) install --upgrade pip setuptools wheel
	$(VENV)/Scripts/activate && $(PIP) install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
	$(VENV)/Scripts/activate && $(PIP) install -r $(BACKEND_DIR)/requirements.txt
	@echo "✓ Backend environment ready (GPU). Activate with: $(VENV)\\Scripts\\activate"

install-frontend: ## Install frontend dependencies
	cd $(FRONTEND_DIR) && npm install
	@echo "✓ Frontend dependencies installed"

install-gateway: ## Install Go gateway dependencies
	cd $(GATEWAY_DIR) && go mod download
	@echo "✓ Gateway dependencies installed"

install-all: install install-frontend install-gateway ## Install backend, frontend and gateway dependencies

# ============================================================
# Development
# ============================================================

dev: ## Start backend dev server
	cd $(BACKEND_DIR) && $(PYTHON) -m nexus.main

dev-frontend: ## Start frontend dev server
	cd $(FRONTEND_DIR) && npm run dev

dev-all: ## Start backend + frontend (requires two terminals)
	@echo "Run in separate terminals:"
	@echo "  Terminal 1: make dev"
	@echo "  Terminal 2: make dev-frontend"

# v2.4: 带完整日志捕获的启动命令（终端输出 + 日志文件）
# 所有终端输出（包括 uvicorn 访问日志、npm 编译日志等）都会写入日志文件
# 日志文件位置: logs/{backend,frontend,go}_logs/

dev-log: ## Start backend dev server with full log capture (PowerShell)
	powershell -ExecutionPolicy Bypass -File scripts/start-backend.ps1

dev-frontend-log: ## Start frontend dev server with full log capture (PowerShell)
	powershell -ExecutionPolicy Bypass -File scripts/start-frontend.ps1

dev-gateway-log: ## Start Go gateway with full log capture (PowerShell)
	powershell -ExecutionPolicy Bypass -File scripts/start-gateway.ps1

# ============================================================
# Docker (Infrastructure)
# ============================================================

docker-up: ## Start all infrastructure services
	docker compose up -d
	@echo "✓ Infrastructure started"

docker-down: ## Stop all infrastructure services
	docker compose down
	@echo "✓ Infrastructure stopped"

docker-logs: ## Show infrastructure logs
	docker compose logs -f

docker-clean: ## Stop and remove all data (CAUTION!)
	docker compose down -v
	@echo "✓ Infrastructure cleaned"

# ============================================================
# Database Init
# ============================================================

init-db: ## Initialize Milvus and Neo4j
	cd $(BACKEND_DIR) && $(PYTHON) -m scripts.init_milvus
	cd $(BACKEND_DIR) && $(PYTHON) -m scripts.init_neo4j
	@echo "✓ Databases initialized"

# ============================================================
# Code Quality
# ============================================================

lint: lint-backend lint-gateway ## Run linters (backend + gateway)
	@echo "✓ All lints passed"

lint-backend: ## Run backend linter (venv or system ruff)
	@if [ -f "$(VENV)/Scripts/ruff" ] || [ -f "$(VENV)/Scripts/ruff.exe" ]; then \
		cd $(BACKEND_DIR) && ../$(VENV)/Scripts/ruff check nexus/ tests/ scripts/; \
	else \
		cd $(BACKEND_DIR) && ruff check nexus/ tests/ scripts/; \
	fi
	@echo "✓ Backend lint passed"

lint-gateway: ## Run Go gateway vet
	cd $(GATEWAY_DIR) && go vet ./...
	@echo "✓ Gateway vet passed"

format: ## Format code (backend)
	cd $(BACKEND_DIR) && $(VENV)/Scripts/ruff format nexus/ tests/ scripts/
	cd $(BACKEND_DIR) && $(VENV)/Scripts/ruff check --fix nexus/ tests/ scripts/
	@echo "✓ Code formatted"

check: ## Run all checks (lint + type check + test + build)
	$(MAKE) lint
	cd $(BACKEND_DIR) && $(VENV)/Scripts/mypy nexus/ --ignore-missing-imports
	cd $(BACKEND_DIR) && $(VENV)/Scripts/pytest tests/ -v
	cd $(GATEWAY_DIR) && go build ./...
	@echo "✓ All checks passed"

# ============================================================
# Testing
# ============================================================

test: ## Run backend tests
	cd $(BACKEND_DIR) && $(VENV)/Scripts/pytest tests/ -v

build-gateway: ## Build Go gateway binary
	cd $(GATEWAY_DIR) && go build ./...

test-cov: ## Run tests with coverage
	cd $(BACKEND_DIR) && $(VENV)/Scripts/pytest tests/ --cov=nexus --cov-report=html

# ============================================================
# Cleanup
# ============================================================

clean: ## Clean build artifacts
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	rm -rf $(BACKEND_DIR)/nexus/__pycache__ $(BACKEND_DIR)/nexus/**/__pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf $(FRONTEND_DIR)/.next
	@echo "✓ Cleaned"
