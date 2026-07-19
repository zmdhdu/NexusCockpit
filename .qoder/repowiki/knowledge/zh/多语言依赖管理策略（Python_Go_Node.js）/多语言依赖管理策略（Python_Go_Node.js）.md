---
kind: dependency_management
name: 多语言依赖管理策略（Python/Go/Node.js）
category: dependency_management
scope:
    - '**'
source_files:
    - backend_design/pyproject.toml
    - backend_design/requirements.txt
    - backend_design/requirements_no_torch.txt
    - backend_design/nexus_gate/go.mod
    - backend_design/nexus_gate/go.sum
    - frontend_design/package.json
    - frontend_design/package-lock.json
    - Makefile
---

本仓库为多语言全栈工程，采用按子模块独立声明、顶层 Makefile 统一编排的依赖管理模式，各语言使用其生态标准工具，无跨语言私有源或 vendoring。

## 1. 使用的系统与工具
- Python 后端：同时维护 pyproject.toml（PEP 621 元数据与可选依赖）与 requirements.txt（精确版本锁定）。构建系统使用 setuptools，开发环境通过 make install / make install-gpu 在 .venv 虚拟环境中安装 PyTorch（CPU/GPU 两个 index-url）及全部依赖。
- Go 网关：位于 backend_design/nexus_gate/，使用 Go Modules（go.mod + go.sum），Go 版本固定为 1.22，未配置 GOPRIVATE 或私有代理。
- Next.js 前端：位于 frontend_design/，使用 npm（package.json + package-lock.json，lockfileVersion=3），通过 make install-frontend 执行 npm install。

## 2. 关键文件与位置
- backend_design/pyproject.toml：项目元数据、运行时依赖（>= 语义）、可选 dev 依赖、ruff/mypy/pytest 配置
- backend_design/requirements.txt：生产级精确版本锁定（含 torch/torchaudio 安装指引注释）
- backend_design/requirements_no_torch.txt：不含 torch 的轻量依赖集（用于某些 CI 场景）
- backend_design/nexus_gate/go.mod / go.sum：Go 模块声明与依赖快照
- frontend_design/package.json / package-lock.json：Node.js 依赖与锁文件
- Makefile：统一的依赖安装入口（.venv 创建、PyTorch 选择、pip/npm 调用）

## 3. 架构与约定
- 双清单并存：pyproject.toml 面向现代 Python 包管理与 IDE 提示，requirements.txt 面向可复现的生产安装；两者需保持版本区间一致。
- PyTorch 分离安装：Makefile 在安装 requirements.txt 之前单独通过 --index-url https://download.pytorch.org/whl/cpu 或 .../cu121 安装 torch/torchaudio，避免 pip 解析冲突。
- 无 vendoring：Go 使用 go.sum 而非 vendor 目录；Python 与 Node.js 均不提交 site-packages/node_modules，依赖由安装阶段拉取。
- 无全局私有源：未发现 pypi 镜像、GOPROXY 或 npm registry 覆盖配置，默认使用官方源（npm lock 中可见 npmmirror.com 作为缓存镜像）。

## 4. 开发者应遵循的规则
1. 新增 Python 依赖：同时在 pyproject.toml 与 requirements.txt 中添加，前者用 >= 约束，后者写死精确版本并更新 requirements_no_torch.txt（若该依赖非 AI 必需）。
2. 升级 PyTorch：优先修改 Makefile 中的 install / install-gpu target 的 index-url，再同步调整 requirements.txt 中 torchaudio 版本。
3. Go 依赖变更：在 nexus_gate/ 下执行 go get 后提交 go.mod 与 go.sum，不要手动编辑。
4. 前端依赖变更：在 frontend_design/ 下执行 npm install，确保 package-lock.json 被提交。
5. 安装入口：始终通过 make install[-gpu|-frontend|-all] 初始化环境，不要直接调用 pip/npm，以免遗漏 PyTorch 特殊安装步骤。