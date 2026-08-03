#!/usr/bin/env python3
"""一次性注释精简脚本：处理含中文弯引号的行内注释"""
import os

f = os.path.join(os.path.dirname(__file__), '..', 'backend_design', 'nexus', 'agent', 'nodes', 'supervisor_node.py')
with open(f, 'r', encoding='utf-8') as fh:
    content = fh.read()

edits = [
    # Edit 1: 关键信息提取 comment
    (
        '        # 关键信息提取 \u2014 从对话历史 + 当前用户输入中提取位置/偏好/身份等关键实体\n        # 这是零 LLM 调用的纯正则匹配，不会增加延迟\n        # 注意：必须包含当前 user_input，否则\u201c我现在在杭州\u201d这类位置信息无法被提取',
        '        # 关键信息提取：纯正则匹配从对话历史+当前输入提取位置/偏好/身份'
    ),
    # Edit 2: GPS补充 comment
    (
        '        # 如果对话历史中没有提取到位置，从车辆适配器获取 GPS 位置补充\n        # 场景: 用户从没说过\u201c我在杭州\u201d，但 GPS 定位在杭州电子科技大学',
        '        # 对话历史无位置时从车辆适配器 GPS 补充'
    ),
    # Edit 3: 阈值压缩 comment
    (
        '        # 阈值压缩 \u2014 对话轮数超阈值时自动压缩旧对话为滚动摘要\n        # 这确保长期对话的关键信息不会因 SessionStore 的 20 条截断而丢失',
        '        # 阈值压缩：对话超阈值时自动压缩旧对话为滚动摘要'
    ),
    # Edit 4: 压缩后的历史 comment
    (
            '            # 更新 state 中的历史为压缩后的版本\n            # 注意：这里不能直接覆盖 state["history"]，因为 history 是 Annotated[list, add] reducer\n            # 压缩后的历史会在后续 build_context 中使用',
            '            # 压缩后的历史在后续 build_context 中使用'
    ),
    # Edit 5: 记忆召回并行 comment
    (
        '        # 记忆召回 + 用户画像 + 意图路由 并行执行\n        # 快速路径: 启发式路由命中的纯车控指令跳过记忆召回和 RAG，\n        # 将 supervisor 延迟从 ~7.5s 降至 <100ms\n        #\n        # 混合意图检测: 当车控指令与非车控意图（如对话历史查询）同时出现时，\n        # 不走快速路径，需要执行记忆召回以支持非车控部分的回答。\n        # 场景: \u201c我问了你哪些问题，同时打开天窗\u201d \u2192 车控走快速执行，\n        # 但对话历史查询需要记忆召回 + LLM 生成回答。\n        #\n        # 复合查询检测: 当文本包含多个子句但启发式只识别了部分意图时，\n        # 不走快速路径，需要 LLM 多意图路由识别剩余需求。\n        # 场景: \u201c帮我查酒旅服务，推荐一些美食，打开车窗\u201d \u2192\n        # 启发式仅识别到 Window_Action，但酒旅和美食需要 LLM 补充识别。',
        '        # 记忆召回+画像+意图路由并行；快速路径跳过召回（<100ms）；混合/复合意图不走快速路径'
    ),
    # Edit 6: 需要记忆召回的场景 comment
    (
            '            # 需要记忆召回的场景:\n            #   - 非车控意图 (正常路径，走完整 LLM 路由 + 记忆召回)\n            #   - 混合意图 (车控 + 非车控，使用启发式结果 + 记忆召回)\n            # 混合意图时车控部分已由启发式路由检测到，不需要再走 LLM 路由，\n            # 但非车控部分（如对话历史查询）需要记忆召回和 LLM 生成回答。',
            '            # 需要记忆召回的场景：非车控意图、混合意图（车控+非车控）'
    ),
    # Edit 7: _route_intent docstring
    (
            '            async def _route_intent():\n                """意图路由\n\n                混合意图优化: 当启发式路由已检测到车控+非车控意图时，\n                直接使用启发式结果，跳过 LLM 路由（节省 1-3s 延迟）。\n                非车控意图走正常 LLM 路由。\n\n                复合查询增强: 当检测到复合查询（文本含多个子句但仅部分被识别）时，\n                走完整路由流程（ctx.intent_router.route()），该流程会自动调用\n                LLM 多意图路由补充识别未匹配的需求。\n                """',
            '            async def _route_intent():\n                """意图路由：混合意图跳过LLM路由，复合查询走完整路由流程"""'
    ),
    # Edit 8: 对话历史查询 comment
    (
        '        # 对话历史查询 \u2014 需要记忆召回 + LLM 生成回答\n        # 场景: \u201c我问了你哪些问题，同时打开天窗\u201d\n        # \u2192 vehicle 专家执行车控，chat 专家回答对话历史查询',
        '        # 对话历史查询：需记忆召回+LLM生成，分派chat专家'
    ),
    # Edit 9: 路由错配 comment
    (
        '        # 路由错配代码检测机制 \u2014 分发目标与指令领域不匹配时记录警告\n        # 场景：车控指令被路由到 navigation/chat 但没有 vehicle 专家',
        '        # 路由错配检测：分发目标与指令领域不匹配时记录警告'
    ),
]

for i, (old, new) in enumerate(edits, 1):
    if old in content:
        content = content.replace(old, new, 1)
        print(f'Edit {i}: OK')
    else:
        print(f'Edit {i}: NOT FOUND')

with open(f, 'w', encoding='utf-8') as fh:
    fh.write(content)
print('File written successfully')
