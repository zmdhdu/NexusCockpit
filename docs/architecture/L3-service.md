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

### base.py — 技能基类 + 装饰器注册 (v2.0)

v2.0 变更:
- 新增 `@register_skill(name, group, has_side_effect, cache_ttl)` 装饰器，技能类标记后自动注册到全局 `_SKILL_REGISTRY` 表
- 新增 `SkillGroup` 枚举，标识技能归属的专家 Agent (VEHICLE/NAVIGATION/LIFESTYLE/HEALTH/CHAT)
- `BaseSkill` 新增 `has_side_effect` / `cache_ttl` 属性，用于缓存安全控制

```python
from nexus.skills.base import BaseSkill, SkillGroup, register_skill

@register_skill("vehicle_climate", SkillGroup.VEHICLE, has_side_effect=True)
class ClimateControlSkill(BaseSkill):
    ...
```

### registry.py — 技能注册中心 (v2.0)

v2.0 从硬编码改为装饰器自动发现 + 手动注册兼容:

```python
from nexus.skills.registry import SkillRegistry

registry = SkillRegistry(graph_store=gs, vehicle_adapter=va)
# 自动扫描 _SKILL_REGISTRY 全局表，实例化所有 @register_skill 标记的技能
# 同时兼容 v1.0 手动 register() 注册

tools = registry.get_all_tools()  # → List[ToolSchema]
result = await registry.execute("vehicle_climate", {"op": "set_temp", "target_temp": 24})

# v2.0 新增: 按专家分组查询
vehicle_skills = registry.get_skills_by_group(SkillGroup.VEHICLE)

# v2.0 新增: 获取有副作用的技能（供缓存层使用）
side_effect_skills = registry.get_side_effect_skills()
```

### 车载技能 (nexus/skills/vehicle/) — 6 个

| 技能 | 文件 | 功能 | 分组 |
|------|------|------|------|
| 空调控制 | `climate.py` | 温度调节、风量、模式 | VEHICLE |
| 车窗控制 | `window.py` | 开关窗、位置 | VEHICLE |
| 座椅控制 | `seat.py` | 位置、加热、通风 | VEHICLE |
| 媒体控制 | `media.py` | 音乐、音量、播放 | VEHICLE |
| 导航 | `navigation.py` | 路线规划、POI | VEHICLE |
| 车辆状态 | `status.py` | 电量、车速、胎压 | VEHICLE |

### 非车载技能 (nexus/skills/special.py) — 3 个 (v1.0)

| 技能 | 功能 | 分组 |
|------|------|------|
| WebSearch | Tavily 联网搜索 | LIFESTYLE |
| FoodDelivery | GraphRAG 餐饮推荐 | LIFESTYLE |
| RegisterVoice | 声纹注册 | CHAT |

### v2.0 新增技能 — 12 个

| 技能 | 文件 | 功能 | 分组 |
|------|------|------|------|
| habit_record | `habit.py` | 记录用户偏好到 Neo4j HABIT 关系 | CHAT |
| habit_recommend | `habit.py` | 查询图谱习惯，主动推荐 | CHAT |
| habit_adjust | `habit.py` | 读取画像，批量下发车控指令 | VEHICLE |
| diagnose_vehicle | `health.py` | 车辆异常问题解读，调取车辆状态 | HEALTH |
| decode_dtc | `health.py` | 故障码释义，查询故障知识库 | HEALTH |
| maintenance_advice | `health.py` | 根据里程/时间生成保养建议 | HEALTH |
| set_reminder | `reminder.py` | 解析时间+内容，持久化存储提醒 | LIFESTYLE |
| query_reminder | `reminder.py` | 查询用户全部待办提醒 | LIFESTYLE |
| cancel_reminder | `reminder.py` | 删除指定提醒 | LIFESTYLE |
| recommend_poi | `local_life.py` | 周边餐饮/景点检索+距离排序 | LIFESTYLE |
| multi_turn_refine | `local_life.py` | 多轮填充推荐槽位，保留上下文 | LIFESTYLE |
| preference_filter | `local_life.py` | 基于用户偏好筛选候选推荐结果 | LIFESTYLE |

### 技能总数: 21 个 (v1.0: 9 + v2.0 新增: 12)

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
