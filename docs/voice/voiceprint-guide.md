# 声纹识别技术文档

> 基于 3D-Speaker CAM++ 的车载声纹识别

## 技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 框架 | 3D-Speaker | 阿里达摩院开源声纹工具包 |
| 模型 | CAM++ | 基于全局上下文注意力的声纹模型，192 维 embedding |
| 部署 | 本地 CPU/GPU | 车载隐私敏感，不上传云端 |

## 模型信息

- **模型名**: CAM++
- **下载路径**: `models/sv/cam_plus/`
- **输出**: 192 维声纹特征向量
- **阈值**: 0.7（可配置 `VOICEPRINT_THRESHOLD`）
- **注册次数**: 3 条音频（可配置 `VOICEPRINT_ENROLL_COUNT`）

## 代码位置

| 文件 | 功能 |
|------|------|
| `backend_design/nexus/core/voiceprint.py` | 声纹服务核心（`VoiceprintService` 类） |
| `backend_design/nexus/api/routes/asr.py` | 声纹注册/验证 API |
| `backend_design/nexus/config.py` | 声纹配置（`ASRConfig` 类） |

## 工作流程

### 注册流程
1. 用户说"注册声纹"
2. 录音 3 次（每次 3-5 秒）
3. 提取 CAM++ embedding
4. 保存到 `assets/speaker/users/{cockpit_id}/{user_id}/enroll_01.npy`

### 验证流程
1. 用户说话
2. 提取当前音频的 CAM++ embedding
3. 与已注册的 embedding 做余弦相似度计算
4. 相似度 > 0.7 → 匹配成功，返回 user_id
5. 匹配成功后触发 `PersonalizationService` 加载用户偏好

## v2.2 修复

### 问题
模型不可用时返回假随机向量（mock 模式），可能导致错误匹配。

### 修复
- 模型不可用时返回 `None` 并记 warn 日志
- 调用方处理 `None` 返回值，跳过声纹验证
- 不再生成假数据，避免"假装验证成功"的安全风险

## 配置

```env
# .env
CAM_MODEL_PATH=./models/sv/cam_plus
VOICEPRINT_THRESHOLD=0.7
VOICEPRINT_ENROLL_COUNT=3
```
