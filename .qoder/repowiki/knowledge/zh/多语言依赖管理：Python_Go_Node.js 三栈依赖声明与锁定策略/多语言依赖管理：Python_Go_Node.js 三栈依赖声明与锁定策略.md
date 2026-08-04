---
kind: dependency_management
name: 多语言依赖管理：Python/Go/Node.js 三栈依赖声明与锁定策略
category: dependency_management
scope:
    - '**'
source_files:
    - backend_design/pyproject.toml
    - backend_design/requirements.txt
    - backend_design/nexus_gate/go.mod
    - frontend_design/package.json
    - frontend_design/package-lock.json
    - Makefile
---

NexusCockpit 项目采用多语言独立依赖管理策略，每个子模块使用各自生态的标准工具进行依赖声明与版本锁定，通过顶层 Makefile 统一编排安装流程。

**后端 Python（backend_design）**
- 双轨依赖声明：`pyproject.toml` 使用 PEP 621 格式声明最小兼容版本范围（如 `fastapi>=0.128.0`），用于现代构建系统；`requirements.txt` 使用精确版本号（如 `fastapi==0.128.0`）配合 `pip install -r requirements.txt` 确保可重现安装
- PyTorch 特殊处理：CPU/GPU 版本通过不同 index-url 分别安装（`https://download.pytorch.org/whl/cpu` 和 `cu121`），在 Makefile 的 `install` 和 `install-gpu` 目标中区分
- 依赖清理：`requirements.txt` 注释明确标注已移除但未使用的包（如 `langgraph-prebuilt`、`langchain-milvus`、`sqlalchemy`、`duckduckgo-search`、`scikit-learn`），保持依赖精简
- 开发依赖分离：通过 `[project.optional-dependencies]` 的 `dev` 组管理测试和 lint 工具

**Go 网关（backend_design/nexus_gate）**
- 标准 Go Modules：`go.mod` 声明 module 名称、Go 版本（1.22）和直接依赖（gin、jwt、websocket、prometheus-client），`go.sum` 锁定所有间接依赖
- 无私有仓库配置：未发现 GOPRIVATE 或 proxy 设置，默认使用 golang.org 官方代理
- 依赖下载：通过 `make install-gateway` 调用 `go mod download` 拉取依赖

**前端 Next.js（frontend_design）**
- npm 依赖管理：`package.json` 声明运行时依赖（Next.js 14.2.5、React 18.3.1、Zustand 等）和开发依赖（TypeScript、TailwindCSS、ESLint）
- 完整锁文件：`package-lock.json` 锁定所有依赖树（lockfileVersion 3），包含 sha512 完整性校验
- 镜像源：从 `package-lock.json` 可见使用 `registry.npmmirror.com`（淘宝镜像）加速国内下载
- 构建脚本：通过 `npm run dev/build/start/lint/type-check` 统一管理

**统一编排（Makefile）**
- 单入口命令：`make install-all` 依次执行 Python venv 创建、PyTorch 安装、requirements 安装、npm 安装、go mod download
- 环境隔离：Python 依赖通过 `.venv` 虚拟环境隔离，Go 和 Node.js 依赖各自目录内管理
- 质量检查：`make check` 串联 ruff lint、mypy 类型检查、pytest 测试、Go build 验证

**约束与约定**
- Python 要求 `>=3.10`，由 `pyproject.toml` 的 `requires-python` 字段强制
- 未使用 vendoring 策略（无 `vendor/` 目录），所有依赖通过包管理器在线安装
- 未发现私有 PyPI 仓库或认证配置，依赖来源均为公共注册表
- Docker 构建中依赖安装通过 `Dockerfile` 和 `docker-compose.yml` 复用上述依赖声明文件