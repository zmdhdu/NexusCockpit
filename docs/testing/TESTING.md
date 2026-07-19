# NexusCockpit 测试方案

> 本文档详细说明项目各模块的测试方法、测试用例和验证步骤�?
> 配合 `docs/deployment/VERIFICATION.md`（逐步验证方案）使用�?

---

## 目录

1. [测试文档总览](#测试文档总览)
2. [单元测试](#单元测试)
3. [集成测试](#集成测试)
4. [前端测试](#前端测试)
5. [API 接口测试](#api-接口测试)
6. [性能测试](#性能测试)
7. [测试命令速查](#测试命令速查)

---

## 测试文档总览

| 测试类型 | 文档位置 | 说明 |
|----------|----------|------|
| 逐步验证方案 | `docs/deployment/VERIFICATION.md` | 8 阶段从环境到全链路的验证 |
| 单元测试代码 | `backend_design/tests/test_core.py` | 车控总线/意图路由/技能注�?Agent 状�?|
| 集成测试代码 | `backend_design/tests/test_api.py` | API 接口端到端测�?|
| 本文�?| `docs/testing/TESTING.md` | 测试用例详细说明 |

---

## 单元测试

### 测试文件: `backend_design/tests/test_core.py`

运行方式:
```bash
cd backend_design
pytest tests/test_core.py -v
```

### 测试用例详情

#### 1. MockVehicleBus 测试 (模拟车控总线)

| 用例 | 测试内容 | 输入 | 预期结果 |
|------|----------|------|----------|
| `test_climate_set_temp` | 设置空调温度 | `op=set_temp, target_temp=24` | 温度=24, 消息�?24" |
| `test_climate_temp_up` | 升高温度 | `op=temp_up` | 温度+1 |
| `test_window_open` | 打开所有车�?| `op=open, position=all` | all=100 |
| `test_window_close` | 关闭左前�?| `op=close, position=front_left` | front_left=0 |
| `test_seat_heat` | 主驾座椅加热 | `op=heat_on, position=driver, level=2` | heat=2 |
| `test_navigation` | 设置导航 | `destination=上海虹桥` | destination正确 |
| `test_media_play` | 播放媒体 | `op=play, source=local` | playing=True |
| `test_vehicle_status` | 查询车辆状�?| 无参�?| 消息�?胎压" |
| `test_invoke_command` | 统一命令入口 | `vehicle_climate, {set_temp:26}` | 温度=26 |
| `test_invoke_unknown_command` | 未知命令 | `unknown_command, {}` | success=False |

#### 2. HeuristicRouter 测试 (启发式意图路�?

| 用例 | 输入文本 | 预期意图 |
|------|----------|----------|
| `test_climate_route` | "把空调调�?4�? | Climate_Action.target_temp=24 |
| `test_window_route` | "打开车窗" | Window_Action.op=open |
| `test_navigation_route` | "导航到上海虹桥火车站" | Navigation_Action.destination�?上海虹桥" |
| `test_media_route` | "播放音乐" | Media_Action.op=play |
| `test_no_match` | "今天天气真好" | 空字�?{} |

#### 3. SkillRegistry 测试 (技能注册中�?

| 用例 | 测试内容 | 预期结果 |
|------|----------|----------|
| `test_list_skills` | 列出所有技�?| 包含 vehicle_climate, web_search, order_food |
| `test_get_all_tools` | 获取 Tool Schema | 数量 >= 9 |
| `test_execute_climate` | 执行空调技�?| status=ok, action=vehicle_climate |
| `test_execute_unknown` | 执行不存在技�?| status=error |

#### 4. AgentState 测试 (Agent 状态模�?

| 用例 | 测试内容 | 预期结果 |
|------|----------|----------|
| `test_default_state` | 默认状�?| user_input="", intent={} |
| `test_custom_state` | 自定义状�?| 正确存储输入�?|

---

## 集成测试

### 测试文件: `backend_design/tests/test_api.py`

运行方式:
```bash
cd backend_design
pytest tests/test_api.py -v
```

> **注意**: 集成测试需要后端服务可启动，但不需要外部中间件 (Milvus/Redis �? 连接成功�?

### 测试用例详情

| 用例 | API | 方法 | 路径 | 预期 |
|------|-----|------|------|------|
| `test_root` | 根路�?| GET | `/` | 200, name=NexusCockpit |
| `test_health` | 健康检�?| GET | `/health` | 200, �?status 字段 |
| `test_admin_skills` | 技能列�?| GET | `/admin/skills` | 200, count >= 0 |
| `test_vehicle_status` | 车辆状�?| GET | `/vehicle/status` | 200, �?success |
| `test_vehicle_command` | 车控命令 | POST | `/vehicle/command` | 200, success=True |

### 手动 API 测试

```bash
# 1. 健康检�?(无需任何 Key)
curl http://localhost:8000/health

# 2. 车控命令 �?设置空调温度 (无需 LLM Key)
curl -X POST http://localhost:8000/vehicle/command \
  -H "Content-Type: application/json" \
  -d '{"command": "vehicle_climate", "arguments": {"op": "set_temp", "target_temp": 24}}'

# 3. 车辆状态查�?
curl http://localhost:8000/vehicle/status

# 4. 技能列�?
curl http://localhost:8000/admin/skills

# 5. 缓存统计
curl http://localhost:8000/admin/cache/stats

# 6. 对话 (需�?ARK_API_KEY)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "把空调调�?4�?, "user_id": "test"}'

# 7. 流式对话 (需�?ARK_API_KEY)
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "你好", "user_id": "test", "stream": true}'

# 8. Prometheus 指标
curl http://localhost:8000/metrics

# 9. Swagger 文档
# 浏览器打开 http://localhost:8000/docs
```

---

## 前端测试

### 页面验证清单

前端不需要单独运行测试，通过浏览器访问验�?

| 页面 | URL | 验证�?|
|------|-----|--------|
| 仪表�?| http://localhost:3000/dashboard | 统计卡片显示、服务状态、缓存统�?|
| 语音助手 | http://localhost:3000/chat | 聊天界面、输入框、流式响�?|
| 车控面板 | http://localhost:3000/vehicle | 6 个控制卡片、按钮点击响�?|
| 设置 | http://localhost:3000/settings | API 密钥、模型配置、数据库状�?|

### 前端独立测试 (无后�?

```bash
cd frontend_design
npm run dev
```

即使后端未启动，前端也应:
- [ ] 所有页面可正常访问 (不白�?
- [ ] 仪表盘使�?Mock 数据展示
- [ ] 车控面板使用 Mock 数据展示
- [ ] 聊天页面显示空状态提�?
- [ ] 控制台无致命错误 (F12 检�?

### 前端联调测试 (有后�?

```bash
# 终端 1: 启动后端
cd backend_design
python -m nexus.main

# 终端 2: 启动前端
cd frontend_design
npm run dev
```

联调验证:
- [ ] 仪表盘服务状态显�?"connected"
- [ ] 车控按钮点击后状态实时更�?
- [ ] 聊天消息发送和接收正常
- [ ] 流式响应逐字显示

---

## 性能测试

### 响应时间基准

| 操作 | P95 目标 | 测试方法 |
|------|----------|----------|
| GET /health | < 50ms | `curl -w "%{time_total}" http://localhost:8000/health` |
| POST /vehicle/command | < 100ms | 前端计时 |
| 缓存命中响应 | < 200ms | 相似查询测试 |
| LLM 首字延迟 | < 2s | 流式首字时间 |
| LLM 完整响应 | < 10s | 非流式总时�?|

### 并发测试

```bash
# 安装 Apache Bench (Windows 可用 wrk 替代)
# 测试 100 个请求，10 并发
ab -n 100 -c 10 -p body.json -T application/json \
  http://localhost:8000/vehicle/command

# body.json:
# {"command": "vehicle_climate", "arguments": {"op": "status"}}
```

### 容错测试

| 场景 | 操作 | 预期行为 |
|------|------|----------|
| Redis 断开 | `docker compose stop redis` | 后端不崩溃，缓存降级 |
| Milvus 断开 | `docker compose stop milvus` | 后端不崩溃，RAG 降级 |
| LLM 超时 | 配置错误 API Key | 熔断器触发，返回降级响应 |

---

## 测试命令速查

```bash
# ==================== 后端测试 ====================

# 运行所有后端测�?
cd backend_design && pytest tests/ -v

# 运行特定测试文件
cd backend_design && pytest tests/test_core.py -v

# 运行特定测试�?
cd backend_design && pytest tests/test_core.py::TestMockVehicleBus -v

# 运行特定测试用例
cd backend_design && pytest tests/test_core.py::TestMockVehicleBus::test_climate_set_temp -v

# 测试覆盖�?
cd backend_design && pytest tests/ --cov=nexus --cov-report=html

# ==================== 前端测试 ====================

# 类型检�?
cd frontend_design && npx tsc --noEmit

# 构建
cd frontend_design && npm run build

# ==================== 代码质量 ====================

# 后端 Lint
cd backend_design && ruff check nexus/ tests/ scripts/

# 后端格式�?
cd backend_design && ruff format nexus/ tests/ scripts/

# ==================== 基础设施 ====================

# 启动全部中间�?
docker compose up -d

# 查看中间件状�?
docker compose ps

# 查看日志
docker compose logs -f

# 停止
docker compose down

# 清理 (含数�?
docker compose down -v
```

---

## 测试环境要求

### 最低要�?(可测试车控和 API)

- Python 3.10+
- Node.js 18+
- 无需 Docker、无需 API Key

可测试内�?
- 单元测试 (全部)
- 集成测试 (车控相关)
- 前端页面 (Mock 模式)

### 完整测试 (可测�?AI 功能)

- Python 3.10+ + 虚拟环境
- Node.js 18+
- Docker (Milvus/Neo4j/Redis/MySQL)
- ARK_API_KEY (火山引擎大模�?
- Tavily API Key (联网搜索)
- 模型文件 (SenseVoice/CosyVoice/CAM++)

可测试内�?
- 全部单元测试 + 集成测试
- LLM 对话
- 流式响应
- 语义缓存
- GraphRAG 检�?
- Multi-Agent 工作�?
- 可观测�?(Prometheus/Grafana/Langfuse)
