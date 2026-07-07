# L3 服务层 (Services)

> 对应代码: `nexus/asr/` + `nexus/tts/` + `nexus/skills/` + `nexus/vehicle/` + `nexus/intent/` + `nexus/mcp/`

## 职责

提供具体的功能服务，被 Agent 层调用：
- **ASR** — 语音识别 + 声纹验证
- **TTS** — 语音合成
- **Skills** — 技能系统 (车控 + 非车控)
- **Vehicle** — 车控总线适配
- **Intent** — 意图路由
- **MCP** — Model Context Protocol 网关

## ASR 引擎 (nexus/asr/engine.py)

### ASREngine — 语音识别

```python
from nexus.asr.engine import ASREngine

asr = ASREngine()
asr.load()                          # 加载 SenseVoice 模型
text = asr.transcribe("audio.wav")  # → "把空调调到24度"
text = asr.transcribe_bytes(wav_bytes)
```

- 基于 FunASR SenseVoice 模型
- 支持多语言、自动检测
- 模型路径: `./models/asr/sensevoice/` (相对路径)

### SpeakerVerifier — 声纹验证

```python
from nexus.asr.engine import SpeakerVerifier

verifier = SpeakerVerifier()
verifier.load()
result = verifier.verify("current.wav", "enrolled.wav")
# → {"match": True, "score": 0.89}
embedding = verifier.extract_embedding("audio.wav")  # → List[float]
```

- 基于 ModelScope CAM++ 模型
- 模型路径: `./models/sv/cam_plus/` (相对路径)
- 声纹音频: `./assets/speaker/` (相对路径)

## TTS 引擎 (nexus/tts/engine.py)

### TTSEngine — 语音合成

```python
from nexus.tts.engine import TTSEngine

tts = TTSEngine()
tts.load()
path = tts.synthesize("好的，已为您将空调调到24度", speaker="中文女声")
for chunk in tts.synthesize_stream(text, speaker="中文女声"):
    # 流式音频块
    pass
```

- 基于 CosyVoice 模型
- 支持预置音色和零样本克隆
- 模型路径: `./models/tts/cosyvoice/` (相对路径)

## 技能系统 (nexus/skills/)

### base.py — 技能基类

所有技能继承 `BaseSkill`，实现 `execute()` 方法。

### registry.py — 技能注册中心

```python
from nexus.skills.registry import SkillRegistry

registry = SkillRegistry(graph_store=gs, vehicle_adapter=va)
tools = registry.get_all_tools()  # → List[ToolSchema]
result = await registry.execute("vehicle_climate", {"op": "set_temp", "target_temp": 24})
```

### 车载技能 (nexus/skills/vehicle/)

| 技能 | 文件 | 功能 |
|------|------|------|
| 空调控制 | `climate.py` | 温度调节、风量、模式 |
| 车窗控制 | `window.py` | 开关窗、位置 |
| 座椅控制 | `seat.py` | 位置、加热、通风 |
| 媒体控制 | `media.py` | 音乐、音量、播放 |
| 导航 | `navigation.py` | 路线规划、POI |
| 车辆状态 | `status.py` | 电量、车速、胎压 |

### 非车载技能 (nexus/skills/special.py)

| 技能 | 功能 |
|------|------|
| WebSearch | Tavily 联网搜索 |
| FoodDelivery | GraphRAG 餐饮推荐 |
| RegisterVoice | 声纹注册 |

## 车控总线 (nexus/vehicle/)

### 适配器模式

```
VehicleAdapter (base.py)
    ├── MockAdapter (mock.py)      — 开发模拟
    ├── HTTPAdapter (http.py)      — HTTP REST 车控
    └── MCPAdapter (mcp.py)        — MCP stdio 车控
```

### factory.py — 适配器工厂

```python
from nexus.vehicle.factory import build_vehicle_adapter

adapter = build_vehicle_adapter()  # 根据 VEHICLE_ADAPTER 环境变量选择
result = await adapter.execute("set_temp", {"target_temp": 24})
```

## 意图路由 (nexus/intent/)

### router.py — 统一路由服务

```python
from nexus.intent.router import IntentRouterService

router = IntentRouterService(tool_catalog=tools)
result = router.route("把空调调到24度")
# → {"intent": "vehicle_climate", "confidence": 0.95, "source": "llm"}
```

### 路由策略 (三级降级)

```
1. LLM 路由 (llm_router.py) — 最高精度，依赖 LLM API
2. 启发式路由 (heuristic.py) — 关键词匹配，零延迟
3. 默认兜底 — 返回 "unknown" 意图
```

## MCP 网关 (nexus/mcp/gateway.py)

```python
from nexus.mcp.gateway import MCPGateway

gateway = MCPGateway()
gateway.register_tool("climate", handler)
result = await gateway.invoke("climate", {"op": "set_temp"})
```

- 实现 Model Context Protocol
- 支持工具注册、发现、调用
- 安全白名单机制
