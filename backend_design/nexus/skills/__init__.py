# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""NexusCockpit Skills 包。

导入技能模块以触发 @register_skill 装饰器注册。

技能清单:
  基础技能 (10个): vehicle_climate/window/seat/navigation/media/status + web_search + order_food + amap_poi_search + register_voice
  扩展技能 (9个): habit_record/recommend/adjust + set/query/cancel_reminder
              + diagnose_vehicle/decode_dtc/maintenance_advice

注: local_life.py 已删除（recommend_poi/multi_turn_refine/preference_filter），
    因为其调用的 search_poi/add_habit 方法在 graph_store 中不存在，为死代码。
"""

# 技能模块导入（触发 @register_skill 装饰器注册）
from nexus.skills import habit  # noqa: F401
from nexus.skills import health  # noqa: F401
from nexus.skills import reminder  # noqa: F401
