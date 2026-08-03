#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量精简冗长流程类注释"""
import os

base = os.path.join(os.path.dirname(__file__), '..', 'backend_design', 'nexus')

edits = {
    # api/routes/chat.py - 模块docstring + 函数docstring
    os.path.join(base, 'api', 'routes', 'chat.py'): [
        # 模块docstring
        (
            '"""\nChat Routes \u2014 文本对话 REST + SSE 接口\n\n核心特性:\n  - 使用 SupervisorGraph 多智能体编排\n  - SSE 流式接口使用 stream_with_events()，输出结构化事件\n  - 支持 checkpoint 持久化（thread_id = session_id）\n  - 缓存检查上移至 Supervisor（CacheGuard 节点）\n  - 集成 SessionStore 持久化会话历史\n  - 集成 Langfuse 链路追踪\n  - has_side_effect 缓存安全隔离\n  - 记录座舱级指标（chat_count / vehicle_cmd_count / latency）到 Redis\n  - 持久化聊天记录到 MySQL chat_logs 表（按 cockpit_id 隔离，管理员不可见内容）\n  - 从请求头 X-Cockpit-Id 获取座舱 ID\n\n流程:\n  1. 限流检查 \u2192 2. 语义缓存查询 \u2192 3. Supervisor 工作流执行 \u2192 4. 指标记录 \u2192 5. 聊天日志持久化 \u2192 6. 写入缓存 \u2192 7. 返回\n"""',
            '"""\nChat Routes \u2014 文本对话 REST + SSE 接口\n\n作用：SupervisorGraph 多智能体编排 + SSE 流式事件 + checkpoint 持久化 + 语义缓存 + 座舱级指标记录；\n场景：车载语音对话的 REST 与 SSE 流式接口。\n"""'
        ),
        # 函数docstring
        (
            '    """文本对话 (非流式)。\n\n    流程: 限流 \u2192 缓存查询 \u2192 Supervisor 执行 \u2192 指标记录 \u2192 日志持久化 \u2192 缓存写入 \u2192 返回\n\n    Args:\n        request: FastAPI 请求对象\n        body: 包含 text、user_id、session_id 的请求体\n\n    Returns:\n        ChatResponse 包含回复文本和延迟信息\n    """',
            '    """文本对话 (非流式)：作用：限流\u2192缓存\u2192Supervisor执行\u2192指标\u2192日志\u2192缓存写入\u2192返回；场景：非流式对话请求。\n\n    Args:\n        request: FastAPI 请求对象\n        body: 包含 text、user_id、session_id 的请求体\n\n    Returns:\n        ChatResponse 包含回复文本和延迟信息\n    """'
        ),
    ],
    # skills/special.py
    os.path.join(base, 'skills', 'special.py'): [
        (
            '        """执行天气查询。\n\n        流程:\n            1. 从 query 中解析日期意图（今天/明天/后天）和城市名\n            2. 如果没有城市名，尝试从 key_context 中提取位置\n            3. 如果仍无城市名，尝试从 GPS 坐标获取位置\n            4. 调用和风天气 API 获取天气数据\n            5. 格式化返回结构化天气信息\n        """',
            '        """执行天气查询：作用：解析日期+城市\u2192调用和风API\u2192格式化返回；场景：用户询问天气。"""'
        ),
    ],
    # skills/reminder_scanner.py
    os.path.join(base, 'skills', 'reminder_scanner.py'): [
        (
            '"""\nReminder Scanner \u2014 后台提醒扫描器\n\n定时扫描 Redis Sorted Set 中的到期提醒，通过 WebSocket 推送通知。\n\n工作流程:\n    1. 每 30 秒扫描一次所有用户的提醒 Sorted Set\n    2. 提取 score <= 当前时间戳的提醒（已到期）\n    3. 通过 WebSocket 连接推送通知\n    4. 从 Sorted Set 中删除已推送的提醒\n"""',
            '"""\nReminder Scanner \u2014 后台提醒扫描器\n\n作用：定时扫描 Redis Sorted Set 到期提醒，通过 WebSocket 推送通知；\n场景：后台定时任务，每 30 秒扫描到期提醒并推送。\n"""'
        ),
    ],
    # skills/registry.py
    os.path.join(base, 'skills', 'registry.py'): [
        (
            '    """技能注册中心。\n\n    初始化流程:\n      1. 扫描 _SKILL_REGISTRY 全局表，获取所有用 @register_skill 标记的技能类\n      2. 实例化每个技能类（通过 factory 回调注入 graph_store / vehicle_adapter 等依赖）\n      3. 同时支持手动 register() 注册\n\n    Args:\n        graph_store: Neo4j 图谱存储（供点餐/习惯技能查询）\n        vehicle_adapter: 车控适配器（供车载技能发送指令）\n    """',
            '    """技能注册中心：作用：扫描全局表自动注册技能 + 手动注册；场景：SupervisorGraph 初始化时实例化所有技能。\n\n    Args:\n        graph_store: Neo4j 图谱存储（供点餐/习惯技能查询）\n        vehicle_adapter: 车控适配器（供车载技能发送指令）\n    """'
        ),
        (
            '        """执行指定技能（带超时控制和瞬时故障重试）。\n\n        改进:\n          1. asyncio.wait_for 超时保护 \u2014 防止外部 API (高德/Tavily) 响应慢阻塞 Agent 流程\n          2. 瞬时故障重试 \u2014 网络抖动等可恢复异常自动重试 (_MAX_RETRIES 次)\n\n        Args:\n            tool_name: 技能名称\n            arguments: 技能参数\n\n        Returns:\n            SkillResult 执行结果\n        """',
            '        """执行指定技能：作用：超时保护+瞬时故障重试，防止外部API慢响应阻塞；场景：所有技能执行入口。\n\n        Args:\n            tool_name: 技能名称\n            arguments: 技能参数\n\n        Returns:\n            SkillResult 执行结果\n        """'
        ),
    ],
    # memory/manager.py
    os.path.join(base, 'memory', 'manager.py'): [
        (
            '        """从用户文本中提取记忆并存储到 Milvus + Neo4j。\n\n        流程:\n            1. LLM 提取三元组（主体-关系-客体）\n            2. 冲突检测（新记忆 vs 现有记忆）\n            3. 冲突裁决：DELETE 旧 / IGNORE 新 / NONE 无冲突\n            4. 双向写入：Milvus 向量 + Neo4j 图谱\n\n        注: 可通过 MEMORY_EXTRACTION_ENABLED=false 关闭以减少 LLM 调用。\n\n        Args:\n            user_text: 用户输入文本\n            user_id: 用户 ID\n\n        Returns:\n            存储的记忆数量\n        """',
            '        """提取记忆并存储：作用：LLM提取三元组\u2192冲突检测\u2192裁决\u2192双向写入Milvus+Neo4j；场景：Reviewer节点记忆存储。\n\n        Args:\n            user_text: 用户输入文本\n            user_id: 用户 ID\n\n        Returns:\n            存储的记忆数量\n        """'
        ),
    ],
    # core/personalization.py
    os.path.join(base, 'core', 'personalization.py'): [
        (
            '    """个性化服务 \u2014 根据声纹识别的用户ID匹配偏好内容。\n\n    核心流程:\n        声纹识别 \u2192 user_id \u2192 读取 JSON 偏好 + MySQL 习惯 \u2192 构建画像文本 \u2192 注入 Prompt\n\n    Attributes:\n        config: 应用配置实例\n        _prefs_dir: 用户偏好 JSON 文件目录\n    """',
            '    """个性化服务：作用：声纹识别\u2192匹配偏好+习惯\u2192构建画像\u2192注入Prompt；场景：用户身份识别后个性化上下文注入。\n\n    Attributes:\n        config: 应用配置实例\n        _prefs_dir: 用户偏好 JSON 文件目录\n    """'
        ),
    ],
    # api/routes/settings.py
    os.path.join(base, 'api', 'routes', 'settings.py'): [
        (
            '    """声纹验证 \u2014 验证成功后自动签发 JWT Token（N9）。\n\n    验证流程:\n    1. 提取音频声纹特征，与该座舱下已注册用户比对\n    2. 验证成功 \u2192 自动签发包含 cockpit_id + user_id + role 的 JWT Token\n    3. 前端可直接使用该 Token 进行后续操作（无需再调用 /auth/token）\n    """',
            '    """声纹验证：作用：声纹比对\u2192验证成功自动签发JWT Token；场景：用户声纹登录，前端直接使用Token无需再调用/auth/token。"""'
        ),
    ],
    # agent/experts/vehicle_expert.py
    os.path.join(base, 'agent', 'experts', 'vehicle_expert.py'): [
        (
            '        """执行单个车控动作。\n\n        流程: 沙箱已审查 \u2192 registry.execute \u2192 沙箱审计日志 \u2192 结果验证\n        异常兜底: 通信超时、硬件无响应、执行异常统一捕获并返回标准化提示\n        """',
            '        """执行单个车控动作：作用：沙箱审查\u2192执行\u2192审计日志\u2192结果验证，异常统一捕获返回标准化提示；场景：车控动作执行。"""'
        ),
    ],
}

total_ok = 0
total_fail = 0
for filepath, file_edits in edits.items():
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    for i, (old, new) in enumerate(file_edits, 1):
        if old in content:
            content = content.replace(old, new, 1)
            total_ok += 1
            print(f'{os.path.basename(filepath)} Edit {i}: OK')
        else:
            total_fail += 1
            print(f'{os.path.basename(filepath)} Edit {i}: NOT FOUND')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

print(f'\nTotal: {total_ok} OK, {total_fail} NOT FOUND')
