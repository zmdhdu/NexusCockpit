# NexusCockpit 前后端逐步验证方案

> 本文档提供从环境搭建到全链路测试的完整验证步骤，按阶段递进执行。

---

## 目录

1. [阶段 1: 环境准备验证](#阶段-1-环境准备验证)
2. [阶段 2: 基础设施启动验证](#阶段-2-基础设施启动验证)
3. [阶段 3: 后端独立验证](#阶段-3-后端独立验证)
4. [阶段 4: 前端独立验证](#阶段-4-前端独立验证)
5. [阶段 5: 前后端联调验证](#阶段-5-前后端联调验证)
6. [阶段 6: AI 功能验证](#阶段-6-ai-功能验证)
7. [阶段 7: 全链路集成测试](#阶段-7-全链路集成测试)
8. [阶段 8: 性能与稳定性验证](#阶段-8-性能与稳定性验证)
9. [附录: 常见问题排查](#附录-常见问题排查)

---

## 阶段 1: 环境准备验证

### 1.1 Python 环境验证

```bash
# 进入项目目录
cd NexusCockpit

# 创建虚拟环境
python -m venv .venv

# 激活 (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# 激活 (Linux/Mac)
source .venv/bin/activate

# 验证 Python 版本
python --version
# 预期: Python 3.10.x 或更高
```

### 1.2 依赖安装验证

```bash
# 安装 PyTorch (CPU 版本)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# 安装项目依赖
pip install -r requirements.txt

# 验证关键依赖
python -c "import fastapi; print(f'FastAPI {fastapi.__version__}')"
python -c "import torch; print(f'PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
python -c "import pymilvus; print(f'PyMilvus {pymilvus.__version__}')"
python -c "import langgraph; print('LangGraph OK')"
python -c "import oss2; print('OSS SDK OK')"
```

**验证清单**:
- [ ] Python 3.10+ 已安装
- [ ] 虚拟环境已创建并激活
- [ ] FastAPI 可导入
- [ ] PyTorch 可导入
- [ ] PyMilvus 可导入
- [ ] LangGraph 可导入
- [ ] oss2 可导入 (OSS SDK)

### 1.3 Node.js 环境验证

```bash
cd frontend_design

# 验证 Node.js
node --version
# 预期: v18.x 或更高

# 安装前端依赖
npm install

# 验证 Next.js
npx next --version
```

**验证清单**:
- [ ] Node.js 18+ 已安装
- [ ] npm install 成功
- [ ] Next.js 可运行

### 1.4 Docker 环境验证

```bash
docker --version
docker compose version

# 验证 Docker 运行
docker info | findstr "Server Version"
```

**验证清单**:
- [ ] Docker 已安装并运行
- [ ] Docker Compose 已安装

---

## 阶段 2: 基础设施启动验证

### 2.1 启动全部中间件

```bash
cd NexusCockpit

# 启动基础设施
docker compose up -d

# 查看状态
docker compose ps
```

**验证清单**:
- [ ] milvus 容器状态为 `running`
- [ ] etcd 容器状态为 `running`
- [ ] minio 容器状态为 `running`
- [ ] neo4j 容器状态为 `running`
- [ ] redis 容器状态为 `running`
- [ ] rabbitmq 容器状态为 `running`
- [ ] mysql 容器状态为 `running`
- [ ] prometheus 容器状态为 `running`
- [ ] grafana 容器状态为 `running`

### 2.2 逐个服务验证

```bash
# Redis 验证
docker exec nexuscockpit-redis-1 redis-cli ping
# 预期: PONG

# RabbitMQ 验证
# 打开 http://localhost:15672 (guest/guest)

# Neo4j 验证
# 打开 http://localhost:7474 (neo4j/nexuscockpit)

# MySQL 验证
docker exec nexuscockpit-mysql-1 mysql -uroot -pnexuscockpit -e "SHOW DATABASES;"
# 预期: 包含 nexus_cockpit

# Milvus 验证 (等待 30 秒后)
curl http://localhost:9091/healthz
# 预期: OK

# Prometheus 验证
# 打开 http://localhost:9090/targets

# Grafana 验证
# 打开 http://localhost:3001 (admin/admin)
```

**验证清单**:
- [ ] Redis 返回 PONG
- [ ] RabbitMQ 管理界面可访问
- [ ] Neo4j Browser 可访问
- [ ] MySQL 数据库存在
- [ ] Milvus 健康检查返回 OK
- [ ] Prometheus targets 正常
- [ ] Grafana 可登录

### 2.3 OSS 连接验证

```bash
# 在项目目录下运行
python -c "
from nexus.config import get_config
from nexus.core.oss import OSSStorage

config = get_config()
print(f'OSS enabled: {config.oss.enabled}')
print(f'Bucket: {config.oss.bucket_name}')
print(f'Endpoint: {config.oss.endpoint}')
print(f'Public URL: {config.oss.public_base_url}')

storage = OSSStorage()
storage.connect()
print(f'OSS available: {storage.is_available}')

# 测试上传
import tempfile, os
with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
    f.write('NexusCockpit OSS test')
    temp_path = f.name

url = storage.upload_file(temp_path, 'test/nexus_test.txt')
print(f'Upload URL: {url}')

# 测试公开访问
import requests
if url:
    resp = requests.get(url)
    print(f'Public read: {resp.status_code} - {resp.text}')

os.unlink(temp_path)
"
```

**验证清单**:
- [ ] OSS 配置正确加载
- [ ] OSS 连接成功
- [ ] 文件上传成功
- [ ] 公开读取可访问

---

## 阶段 3: 后端独立验证

### 3.1 配置验证

```bash
cd NexusCockpit

# 验证 .env 配置
python -c "
from nexus.config import get_config
c = get_config()
print('=== Configuration Check ===')
print(f'LLM Model: {c.llm.llm_model}')
print(f'ARK API Key: {\"✓ set\" if c.llm.ark_api_key else \"✗ empty\"}')
print(f'Tavily Key: {\"✓ set\" if c.tavily.api_key else \"✗ empty\"}')
print(f'Milvus URI: {c.milvus.uri}')
print(f'Neo4j URI: {c.neo4j.uri}')
print(f'Redis URL: {c.redis.url}')
print(f'ASR Path: {c.asr.resolved_funasr_path()}')
print(f'TTS Path: {c.asr.resolved_cosyvoice_path()}')
print(f'SV Path: {c.asr.resolved_cam_path()}')
print(f'OSS Enabled: {c.oss.enabled}')
print(f'Vehicle Adapter: {c.vehicle.adapter}')
"
```

**验证清单**:
- [ ] ARK_API_KEY 已填入
- [ ] TAVILY_API_KEY 已填入
- [ ] 所有路径为相对路径
- [ ] OSS 已启用
- [ ] Vehicle Adapter 为 mock

### 3.2 数据库初始化验证

```bash
# 初始化 Milvus
cd backend_design && python -m scripts.init_milvus
# 预期: 创建 Food_List 与 User_Memory collection

# 初始化 Neo4j
cd backend_design && python -m scripts.init_neo4j
# 预期: 创建约束和索引
```

**验证清单**:
- [ ] Milvus 初始化成功
- [ ] Neo4j 初始化成功

### 3.3 后端启动验证

```bash
# 启动后端 (注意需在 backend_design 目录下执行)
cd backend_design && python -m nexus.main

# 或使用 uvicorn
cd backend_design && uvicorn nexus.main:app --host 0.0.0.0 --port 8000 --reload
```

**验证清单**:
- [ ] 无启动错误
- [ ] 日志显示 "NexusCockpit ready!"
- [ ] Milvus 连接成功
- [ ] Neo4j 连接成功
- [ ] Redis 连接成功
- [ ] OSS 连接成功
- [ ] Agent graph 初始化成功

### 3.4 API 接口验证

```bash
# 健康检查
curl http://localhost:8000/health
# 预期: {"status": "healthy", "services": {...}}

# Swagger 文档
# 打开 http://localhost:8000/docs

# 测试车控命令 (不需要 LLM Key)
curl -X POST http://localhost:8000/vehicle/command \
  -H "Content-Type: application/json" \
  -d '{"command": "vehicle_climate", "arguments": {"op": "set_temp", "target_temp": 24}}'
# 预期: {"success": true, "result": {"current_temp": 24}}

# 测试车控状态
curl http://localhost:8000/vehicle/status
# 预期: 返回车辆完整状态 JSON

# 测试技能列表
curl http://localhost:8000/admin/skills
# 预期: 返回 9 个技能的 tool schema

# 测试缓存统计
curl http://localhost:8000/admin/cache/stats
# 预期: 返回缓存命中/未命中统计

# 测试对话 (需要 ARK_API_KEY)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "你好", "user_id": "test"}'
# 预期: 返回 LLM 响应

# 测试车控对话
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "把空调调到24度", "user_id": "test"}'
# 预期: 返回车控执行结果

# Prometheus 指标
curl http://localhost:8000/metrics
# 预期: 返回 Prometheus 格式指标
```

**验证清单**:
- [ ] 健康检查返回 healthy
- [ ] Swagger 文档可访问
- [ ] 车控命令执行成功
- [ ] 车辆状态查询成功
- [ ] 技能列表正常
- [ ] 缓存统计可获取
- [ ] 对话 API 正常 (需 API Key)
- [ ] Prometheus 指标可获取

---

## 阶段 4: 前端独立验证

### 4.1 前端启动

```bash
cd frontend_design

# 复制环境变量
cp .env.local.example .env.local

# 开发模式启动
npm run dev
```

### 4.2 页面验证

逐个访问以下页面:

| 页面 | URL | 预期效果 |
|------|-----|----------|
| 仪表盘 | http://localhost:3000/dashboard | 显示统计卡片、服务状态、缓存统计 |
| 语音助手 | http://localhost:3000/chat | 显示聊天界面、输入框 |
| 车控面板 | http://localhost:3000/vehicle | 显示空调、车窗、座椅、媒体、导航卡片 |
| 设置 | http://localhost:3000/settings | 显示 API 密钥、模型配置、数据库状态 |

### 4.3 前端独立功能验证

**无后端时的验证 (Mock 模式)**:

1. **仪表盘页面**:
   - [ ] 4 个统计卡片正常显示
   - [ ] 服务状态显示 "offline" (后端未启动时)
   - [ ] 缓存统计显示 "—"
   - [ ] 页面暗色主题正确

2. **车控面板**:
   - [ ] 6 个控制卡片正常显示
   - [ ] 顶部显示"后端离线"提示条
   - [ ] 使用 Mock 数据填充 (明确标注为模拟数据)
   - [ ] 点击按钮时弹出 toast 错误提示 (UI 不崩溃)

3. **聊天页面**:
   - [ ] 显示空状态提示
   - [ ] 输入框可输入
   - [ ] 发送消息时显示 "思考中..."
   - [ ] API 失败时显示 toast 错误提示
   - [ ] 流式输出时显示"停止"按钮

4. **设置页面**:
   - [ ] 4 个设置卡片正常显示
   - [ ] 模型信息正确
   - [ ] 数据库状态列表显示

**验证清单**:
- [ ] 所有 4 个页面可正常访问
- [ ] 暗色主题渲染正确
- [ ] 玻璃拟态效果可见
- [ ] 侧边栏导航功能正常
- [ ] 无控制台错误 (F12 检查)
- [ ] Toast 通知正常弹出

---

## 阶段 5: 前后端联调验证

### 5.1 启动前后端

```bash
# 终端 1: 启动后端
cd NexusCockpit
.\.venv\Scripts\Activate.ps1
cd backend_design && python -m nexus.main

# 终端 2: 启动前端
cd NexusCockpit/frontend_design
npm run dev
```

### 5.2 联调验证

1. **仪表盘联调**:
   - [ ] 服务状态显示 "connected" / "ready"
   - [ ] 缓存统计显示真实数据
   - [ ] 系统状态显示 "系统正常"

2. **车控面板联调**:
   - [ ] 点击 "24°" 按钮后空调温度变为 24
   - [ ] 点击 "全开" 按钮后车窗全部打开
   - [ ] 点击 "播放" 按钮后媒体状态变化
   - [ ] 点击 "导航到上海虹桥" 后导航设置成功
   - [ ] 所有按钮点击后弹出 toast 成功提示
   - [ ] 所有按钮点击后状态实时刷新

3. **聊天联调** (需要 ARK_API_KEY):
   - [ ] 输入 "把空调调到24度" 后返回车控执行结果
   - [ ] 输入 "今天天气怎么样" 后返回搜索结果
   - [ ] 输入 "你好" 后返回 LLM 响应
   - [ ] 流式响应逐字显示
   - [ ] 消息时间戳正常
   - [ ] 意图标签显示
   - [ ] 助手回复支持 Markdown 渲染
   - [ ] 流式输出时可点击"停止"按钮取消
   - [ ] 刷新页面后对话历史保留 (persist)

4. **设置联调**:
   - [ ] 后端连接状态显示 "已连接"
   - [ ] 数据库状态全部 "运行中"

**验证清单**:
- [ ] 前端能正确调用后端 API
- [ ] CORS 配置正确 (无跨域错误)
- [ ] 前端直连后端 (http://localhost:8000)
- [ ] 所有车控操作成功
- [ ] 聊天功能正常
- [ ] Toast 通知正常弹出

---

## 阶段 6: AI 功能验证

> 此阶段需要配置 ARK_API_KEY

### 6.1 LLM 对话验证

```bash
# 基础对话
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，请介绍一下你自己", "user_id": "test"}'

# 车控指令
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "把空调调到26度", "user_id": "test"}'

# 搜索指令
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "今天北京天气怎么样", "user_id": "test"}'

# 点餐指令
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "我想吃汉堡", "user_id": "test"}'
```

### 6.2 流式响应验证

```bash
# SSE 流式
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "给我讲个故事", "user_id": "test", "stream": true}'
```

### 6.3 Multi-Agent 验证

通过前端聊天界面测试:
- [ ] Planner 正确识别意图
- [ ] Executor 正确调度技能
- [ ] Responder 正确生成响应
- [ ] Reviewer 正确存储记忆

### 6.4 语义缓存验证

```bash
# 第一次查询 (未命中缓存)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "把空调调到25度", "user_id": "test"}'

# 查看缓存统计
curl http://localhost:8000/admin/cache/stats
# 预期: misses = 1

# 相似查询 (应命中缓存)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "空调温度设为25度", "user_id": "test"}'

# 再次查看缓存统计
curl http://localhost:8000/admin/cache/stats
# 预期: hits = 1 (或增加)
```

**验证清单**:
- [ ] LLM 对话正常
- [ ] 车控指令通过 Agent 执行
- [ ] 搜索技能正常
- [ ] 点餐技能正常
- [ ] 流式响应逐字输出
- [ ] 语义缓存命中

---

## 阶段 7: 全链路集成测试

### 7.1 OSS 存储验证

```bash
# 通过 API 上传文件
curl -X POST http://localhost:8000/admin/upload \
  -F "file=@test.wav" \
  -F "path=audio/test"

# 验证 OSS 公开访问
# 打开返回的 URL
```

### 7.2 可观测性验证

1. **Langfuse** (如已配置):
   - [ ] 打开 Langfuse Dashboard
   - [ ] 查看 Agent 调用链
   - [ ] 查看 LLM 调用详情

2. **Prometheus + Grafana**:
   - [ ] 打开 http://localhost:9090/targets
   - [ ] 确认 nexus target 正常
   - [ ] 打开 http://localhost:3001
   - [ ] 查看 NexusCockpit Dashboard

3. **结构化日志**:
   - [ ] 后端控制台输出 JSON 格式日志
   - [ ] 包含 trace_id、user_id 等字段

### 7.3 WebSocket 验证

```javascript
// 在浏览器控制台执行
const ws = new WebSocket("ws://localhost:8000/ws/chat");
ws.onopen = () => {
  ws.send(JSON.stringify({text: "你好", user_id: "test"}));
};
ws.onmessage = (event) => {
  console.log(JSON.parse(event.data));
};
```

**验证清单**:
- [ ] OSS 上传/下载正常
- [ ] Langfuse 追踪可见 (如配置)
- [ ] Grafana 面板数据正常
- [ ] Prometheus 指标采集正常
- [ ] WebSocket 连接正常

---

## 阶段 8: 性能与稳定性验证

### 8.1 响应时间验证

| 操作 | P95 目标 | 验证方法 |
|------|----------|----------|
| 健康检查 | < 50ms | `curl -w "%{time_total}" http://localhost:8000/health` |
| 车控命令 | < 100ms | 通过前端计时 |
| 缓存命中响应 | < 200ms | 相似查询测试 |
| LLM 首字延迟 | < 2s | 流式响应首字时间 |
| LLM 完整响应 | < 10s | 非流式响应总时间 |

### 8.2 并发验证

```bash
# 使用 Apache Bench 或 wrk 进行并发测试
ab -n 100 -c 10 -p body.json -T application/json http://localhost:8000/vehicle/command

# body.json 内容:
# {"command": "vehicle_climate", "arguments": {"op": "status"}}
```

### 8.3 错误恢复验证

1. **Redis 断开**:
   - 停止 Redis: `docker compose stop redis`
   - 验证: 后端不崩溃，缓存降级为直通
   - 恢复: `docker compose start redis`

2. **Milvus 断开**:
   - 停止 Milvus: `docker compose stop milvus`
   - 验证: 后端不崩溃，RAG 检索降级
   - 恢复: `docker compose start milvus`

3. **LLM API 超时**:
   - 配置错误的 ARK_API_KEY
   - 验证: 熔断器触发，返回降级响应

**验证清单**:
- [ ] 响应时间达标
- [ ] 并发 10 请求无错误
- [ ] Redis 断开后自动降级
- [ ] Milvus 断开后自动降级
- [ ] LLM 超时后熔断器触发

---

## 附录: 常见问题排查

### Q: 后端启动报 ModuleNotFoundError

```bash
# 确保虚拟环境已激活
.\.venv\Scripts\Activate.ps1

# 确保在 backend_design 目录下执行
cd backend_design

# 重新安装依赖
pip install -r requirements.txt
```

### Q: 前端 API 请求 404

前端通过 axios 直连后端 (http://localhost:8000)，不依赖 Next.js rewrites 代理。请确认:
1. 后端已启动并监听 8000 端口
2. `.env.local` 中 `NEXT_PUBLIC_API_URL` 配置正确
3. 后端路由路径与前端请求路径一致

### Q: CORS 错误

后端已配置允许所有来源 (`*`)，如果仍有问题检查:
```python
# nexus/main.py 中的 CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Q: Milvus 连接超时

```bash
# 检查 Milvus 是否完全启动
docker compose logs milvus | tail -20

# Milvus 首次启动可能需要 30-60 秒
# 等待后重试
```

### Q: OSS 上传失败

```bash
# 检查 OSS 配置
python -c "
from nexus.config import get_config
c = get_config()
print(f'Access Key: {c.oss.access_key[:10]}...')
print(f'Bucket: {c.oss.bucket_name}')
print(f'Endpoint: {c.oss.endpoint}')
"

# 检查网络连通性
ping oss-cn-beijing.aliyuncs.com
```

### Q: LLM 返回空响应

- 检查 ARK_API_KEY 是否正确
- 检查网络是否能访问 ark.cn-beijing.volces.com
- 查看后端日志中的错误信息

### Q: 前端样式异常

```bash
# 清除 Next.js 缓存
cd frontend_design
rm -rf .next
npm run dev
```
