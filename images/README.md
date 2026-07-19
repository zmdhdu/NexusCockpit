# images/ — README 展示图片目录

> 本目录存放 `README.md` 和 `Agent.md` 中引用的所有展示图片。
> 截图后请按下方清单的文件名保存到对应子目录，README 中的图片引用即可自动生效。

---

## 截图清单

### 📱 `frontend/` — 前端界面截图

| 文件名 | 对应页面 | URL | 说明 |
|--------|----------|-----|------|
| `cockpit-main.png` | 座舱控制台主界面 | http://localhost:3000/cockpit | 座舱页面整体截图，展示聊天区+车控区+3D 可视化 |
| `cockpit-chat.png` | 语音对话与车控联动 | http://localhost:3000/cockpit | 演示一次完整的语音对话→车控执行流程 |
| `cockpit-multi.png` | 座舱控制 | http://localhost:3000/cockpit | 展示座舱控制台/车控面板效果 |
| `chat-page.png` | 聊天对话页面 | http://localhost:3000/chat | 独立聊天页面，展示 SSE 流式输出+Markdown 渲染 |
| `settings.png` | 设置中心 | http://localhost:3000/settings | 座舱/用户/中间件管理界面 |
| `admin.png` | 管理后台 | http://localhost:3000/admin | 系统管理页面，用户权限+座舱注册 |
| `vehicle.png` | 车控模拟器 | http://localhost:3000/vehicle | 车控模拟页面，空调/车窗/灯光等操控 |

### 📊 `dashboard/` — 监控看板截图

| 文件名 | 对应页面 | URL | 说明 |
|--------|----------|-----|------|
| `dataplatform.png` | 数据中台看板 | http://localhost:3000/dataplatform | 跨座舱数据统计与分析平台 |
| `middleware-monitor.png` | 中间件监控看板 | http://localhost:3000/middleware | Milvus/Neo4j/Redis/RabbitMQ/MySQL 状态监控 |
| `grafana.png` | Grafana 监控面板 | http://localhost:3001 | Prometheus 指标 + Grafana 可视化看板 |

### 🏗️ `architecture/` — 架构设计图（可选）

| 文件名 | 说明 |
|--------|------|
| `7-layer-arch.png` | 7 层分层架构图 |
| `multi-agent-flow.png` | Multi-Agent 工作流图 (Supervisor + 5 Experts) |
| `graphrag-flow.png` | GraphRAG 三路融合检索流程图 |
| `cockpit-arch.png` | 座舱控制 + 运营总览架构图 |

### 📦 `misc/` — 其他截图（可选）

| 文件名 | 说明 |
|--------|------|
| `docker-ps.png` | `docker compose ps` 所有服务 running 的截图 |
| `swagger-ui.png` | FastAPI Swagger UI 文档页面截图 |
| `health-check.png` | 健康检查返回截图 |

---

## 命名规范

1. **格式**：统一使用 `.png` 格式（透明背景用 `.png`，照片用 `.jpg`）
2. **命名**：全小写英文，单词间用 `-` 分隔，如 `cockpit-main.png`
3. **尺寸**：建议宽度 1200px-1920px，高度不限
4. **压缩**：上传前建议用 [TinyPNG](https://tinypng.com/) 压缩，单张不超过 500KB

## 截图步骤

```bash
# 1. 启动全部服务
docker compose up -d          # 基础设施
make dev                      # 后端 (端口 8000)
cd backend_design/nexus_gate && go run cmd/main.go  # 网关 (端口 8080)
make dev-frontend             # 前端 (端口 3000)

# 2. 逐页面截图
# 浏览器打开对应 URL → F12 调整到合适分辨率 → 截图 → 保存到 images/ 对应子目录

# 3. 提交
git add images/
git commit -m "docs: add frontend/dashboard screenshots"
git push
```

## 在 README 中引用方式

```markdown
![座舱控制台主界面](images/frontend/cockpit-main.png)
```

> 如果图片路径正确但 GitHub 上不显示，请检查：
> 1. 文件名大小写是否完全匹配（Linux 区分大小写）
> 2. 文件是否已 `git add` 并 `git push`
> 3. 路径是否使用 `/` 而非 `\`
