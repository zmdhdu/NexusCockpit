"""NexusCockpit Skills 包。

v2.0 新增: 导入新技能模块以触发 @register_skill 装饰器注册。

技能清单:
  v1.0 (9个): vehicle_climate/window/seat/navigation/media/status + web_search + order_food + register_voice
  v2.0 (12个): habit_record/recommend/adjust + set/query/cancel_reminder
              + diagnose_vehicle/decode_dtc/maintenance_advice
              + recommend_poi/multi_turn_refine/preference_filter
"""

# v2.0 新增技能模块导入（触发 @register_skill 装饰器注册）
from nexus.skills import habit  # noqa: F401
from nexus.skills import health  # noqa: F401
from nexus.skills import local_life  # noqa: F401
from nexus.skills import reminder  # noqa: F401
