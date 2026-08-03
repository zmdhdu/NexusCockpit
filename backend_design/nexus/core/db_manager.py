# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
MySQL 鏁版嵁搴撶鐞嗗櫒 鈥?缁熶竴鏁版嵁搴撹闂眰

鎻愪緵杩炴帴姹犵鐞嗗拰鎵€鏈?MySQL 琛ㄧ殑 CRUD 鎿嶄綔锛?
- SubAgent/MainAgent 宸℃鏃ュ織
- 瀹¤鏃ュ織
- LLM 鎴愭湰杩借釜
- 鐢ㄦ埛绠＄悊锛圧BAC锛?
- 瀵硅瘽鍘嗗彶

浣跨敤 aiomysql 寮傛椹卞姩锛屾敮鎸佽繛鎺ユ睜銆?
"""

from __future__ import annotations

import json
import warnings
from datetime import datetime
from typing import Any

import aiomysql

from nexus.config import get_config
from nexus.core.logger import get_logger

logger = get_logger(__name__)

# 鎶戝埗 MySQL 'Table already exists' warning 鈥斺€?CREATE TABLE IF NOT EXISTS
# 瀵瑰凡瀛樺湪鐨勮〃浼氬彂鍑?warning锛宎iomysql 灏嗗叾杞彂鍒?Python warnings 妯″潡锛?
# 姣忔鍚姩閮戒細杈撳嚭 12+ 鏉℃棤鐢?warning銆傚湪妯″潡绾ц繃婊わ紝淇濇寔鏃ュ織骞插噣銆?
warnings.filterwarnings(
    "ignore", message=r"Table '.*' already exists", category=Warning,
)


class DatabaseManager:
    """MySQL 鏁版嵁搴撶鐞嗗櫒鍗曚緥銆?

    浣跨敤 aiomysql.create_pool 鍒涘缓杩炴帴姹狅紝
    鎵€鏈夋煡璇㈤€氳繃姹犲寲杩炴帴鎵ц锛岄伩鍏嶉绻佸垱寤?閿€姣佽繛鎺ャ€?

    Usage:
        db = DatabaseManager()
        await db.connect()
        await db.insert_subagent_log(...)
    """

    def __init__(self) -> None:
        self._pool: aiomysql.Pool | None = None
        self._connected = False

    async def connect(self) -> None:
        """鍒濆鍖栬繛鎺ユ睜銆?""
        if self._connected:
            return

        config = get_config().mysql
        try:
            self._pool = await aiomysql.create_pool(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                db=config.database,
                charset="utf8mb4",
                autocommit=True,
                minsize=2,
                maxsize=10,
            )
            self._connected = True
            logger.info(f"MySQL pool connected: {config.host}:{config.port}/{config.database}")

            # 鑷姩杩佺Щ锛氱‘淇濆浼氳瘽琛ㄥ拰鍒楀瓨鍦?
            await self._auto_migrate_tables()

            # 鑷姩淇宸叉湁涓枃鐢ㄦ埛鍚?鈫?鑻辨枃锛堥伩鍏嶇紪鐮佷贡鐮侊級
            await self._auto_fix_chinese_usernames()
        except Exception as e:
            logger.error(f"MySQL connection failed: {e}")
            self._connected = False

    async def _auto_migrate_tables(self) -> None:
        """鍚姩鏃惰嚜鍔ㄨ縼绉?鈥?纭繚 鍏ㄩ儴琛ㄥ拰鍒楀瓨鍦ㄣ€?

        鑷姩鍒涘缓浠ヤ笅琛紙IF NOT EXISTS锛?
        1. cockpits 鈥?搴ц埍琛?
        2. users 鈥?鐢ㄦ埛琛紙RBAC 鍥涚骇瑙掕壊锛?
        3. chat_history 鈥?瀵硅瘽鍘嗗彶琛?
        4. cockpit_stats 鈥?搴ц埍浣跨敤缁熻琛?
        5. subagent_logs 鈥?SubAgent 宸℃鏃ュ織
        6. mainagent_logs 鈥?MainAgent 纭鏃ュ織
        7. audit_logs 鈥?瀹¤鏃ュ織琛?
        8. agent_feedback 鈥?鐢ㄦ埛鍙嶉琛?
        9. llm_cost_tracking 鈥?LLM 鎴愭湰杩借釜琛?
        10. voiceprint_enrollments 鈥?澹扮汗娉ㄥ唽璁板綍琛?
        11. chat_sessions 鈥?澶氫細璇濈鐞嗚〃
        12. user_habits 鈥?鐢ㄦ埛涔犳儻璁板綍琛?
        13. chat_logs 琛ㄧ殑 session_id 鍒楋紙浼氳瘽娑堟伅鍏宠仈锛?
        14. 鎻掑叆榛樿搴ц埍鍜岀敤鎴锋暟鎹?
        """
        if not self.is_connected:
            return
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS cockpits ("
                        "  cockpit_id VARCHAR(32) PRIMARY KEY,"
                        "  name VARCHAR(64) NOT NULL,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  vehicle_adapter VARCHAR(32) DEFAULT 'mock',"
                        "  redis_db INT DEFAULT 0,"
                        "  milvus_prefix VARCHAR(64) DEFAULT '',"
                        "  theme_color VARCHAR(16) DEFAULT '#4fc3f7',"
                        "  is_active BOOLEAN DEFAULT TRUE,"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                        "  INDEX idx_active (is_active)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 2. 鍒涘缓 users 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS users ("
                        "  user_id VARCHAR(64) PRIMARY KEY,"
                        "  username VARCHAR(64) NOT NULL,"
                        "  password_hash VARCHAR(256),"
                        "  cockpit_id VARCHAR(32),"
                        "  role ENUM('super_admin', 'cockpit_admin', 'cockpit_user', 'cockpit_viewer')"
                        "    DEFAULT 'cockpit_user',"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  INDEX idx_cockpit (cockpit_id),"
                        "  INDEX idx_role (role)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 3. 鍒涘缓 chat_history 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS chat_history ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  session_id VARCHAR(128),"
                        "  user_input TEXT NOT NULL,"
                        "  assistant_reply TEXT,"
                        "  intent VARCHAR(64),"
                        "  experts_involved JSON,"
                        "  latency_ms FLOAT DEFAULT 0,"
                        "  cache_hit BOOLEAN DEFAULT FALSE,"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  INDEX idx_cockpit_time (cockpit_id, created_at),"
                        "  INDEX idx_user_time (user_id, created_at),"
                        "  INDEX idx_session (session_id)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 4. 鍒涘缓 cockpit_stats 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS cockpit_stats ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  stat_time DATETIME NOT NULL,"
                        "  chat_count INT DEFAULT 0,"
                        "  vehicle_cmd_count INT DEFAULT 0,"
                        "  cache_hits INT DEFAULT 0,"
                        "  cache_misses INT DEFAULT 0,"
                        "  avg_latency_ms FLOAT DEFAULT 0,"
                        "  p95_latency_ms FLOAT DEFAULT 0,"
                        "  error_count INT DEFAULT 0,"
                        "  INDEX idx_cockpit_time (cockpit_id, stat_time)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 5. 鍒涘缓 subagent_logs 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS subagent_logs ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  check_time DATETIME NOT NULL,"
                        "  check_items JSON,"
                        "  llm_judgment JSON,"
                        "  decision_trace JSON,"
                        "  is_anomaly BOOLEAN DEFAULT FALSE,"
                        "  INDEX idx_cockpit_time (cockpit_id, check_time)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 6. 鍒涘缓 mainagent_logs 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS mainagent_logs ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  alert_time DATETIME NOT NULL,"
                        "  alert_type VARCHAR(64),"
                        "  severity VARCHAR(16),"
                        "  subagent_judgment JSON,"
                        "  mainagent_judgment JSON,"
                        "  action_taken VARCHAR(32),"
                        "  confirm_time DATETIME,"
                        "  INDEX idx_cockpit_time (cockpit_id, alert_time)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 7. 鍒涘缓 audit_logs 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS audit_logs ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  action VARCHAR(64) NOT NULL,"
                        "  detail JSON,"
                        "  ip_address VARCHAR(45),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  INDEX idx_cockpit_time (cockpit_id, created_at),"
                        "  INDEX idx_user_time (user_id, created_at)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 8. 鍒涘缓 agent_feedback 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS agent_feedback ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  mainagent_log_id BIGINT,"
                        "  feedback ENUM('positive', 'negative') NOT NULL,"
                        "  comment TEXT,"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  INDEX idx_cockpit_time (cockpit_id, created_at)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 9. 鍒涘缓 llm_cost_tracking 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS llm_cost_tracking ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  request_type VARCHAR(32) NOT NULL,"
                        "  model_name VARCHAR(64) NOT NULL,"
                        "  prompt_tokens INT DEFAULT 0,"
                        "  completion_tokens INT DEFAULT 0,"
                        "  cost_yuan DECIMAL(10, 6) DEFAULT 0,"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  INDEX idx_cockpit_time (cockpit_id, created_at),"
                        "  INDEX idx_type_time (request_type, created_at)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 10. 鍒涘缓 voiceprint_enrollments 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS voiceprint_enrollments ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  enroll_count INT DEFAULT 0,"
                        "  required_count INT DEFAULT 3,"
                        "  is_completed BOOLEAN DEFAULT FALSE,"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                        "  UNIQUE KEY uk_cockpit_user (cockpit_id, user_id),"
                        "  INDEX idx_cockpit (cockpit_id)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                    )

                    # 11. 鍒涘缓 chat_sessions 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS chat_sessions ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  session_id VARCHAR(128) NOT NULL UNIQUE,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  title VARCHAR(128) DEFAULT '鏂板璇?,"
                        "  message_count INT DEFAULT 0,"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  last_message_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                        "  INDEX idx_cockpit_time (cockpit_id, last_message_at),"
                        "  INDEX idx_user (user_id)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
                    )

                    # 12. 鍒涘缓 user_habits 琛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS user_habits ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  habit_key VARCHAR(128) NOT NULL,"
                        "  habit_value TEXT,"
                        "  hit_count INT DEFAULT 1,"
                        "  last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  UNIQUE KEY uk_user_cockpit_habit (user_id, cockpit_id, habit_key),"
                        "  INDEX idx_user (user_id),"
                        "  INDEX idx_cockpit (cockpit_id)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
                    )

                    # 11.5 鍒涘缓 chat_logs 琛紙瀵硅瘽鏃ュ織鎸佷箙鍖?鈥?鐢ㄦ埛鎻愰棶 + AI鍥炲鍙屽悜瀛樺偍锛?
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS chat_logs ("
                        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                        "  cockpit_id VARCHAR(32) NOT NULL,"
                        "  user_id VARCHAR(64) NOT NULL,"
                        "  session_id VARCHAR(128) DEFAULT '',"
                        "  user_input TEXT NOT NULL,"
                        "  assistant_response TEXT,"
                        "  intent VARCHAR(64) DEFAULT '',"
                        "  action VARCHAR(64) DEFAULT '',"
                        "  latency_ms FLOAT DEFAULT 0,"
                        "  cache_hit BOOLEAN DEFAULT FALSE,"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  INDEX idx_cockpit_time (cockpit_id, created_at),"
                        "  INDEX idx_session (session_id),"
                        "  INDEX idx_user_time (user_id, created_at)"
                        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
                    )

                    # 3. 涓?chat_logs 琛ㄦ坊鍔?session_id 鍒楋紙濡傛灉涓嶅瓨鍦級
                    await cur.execute(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() AND table_name = 'chat_logs' "
                        "AND column_name = 'session_id'"
                    )
                    row = await cur.fetchone()
                    if row and row[0] == 0:
                        await cur.execute(
                            "ALTER TABLE chat_logs ADD COLUMN session_id VARCHAR(128) DEFAULT ''"
                        )
                        await cur.execute(
                            "ALTER TABLE chat_logs ADD INDEX idx_session (session_id)"
                        )
                        logger.info("Auto-migrate: added session_id column to chat_logs")

                    # 14. 鎻掑叆榛樿搴ц埍鍜岀敤鎴锋暟鎹紙ON DUPLICATE KEY UPDATE锛?
                    # MySQL 8.0+ 寮冪敤浜?VALUES(col) 璇硶锛屾敼鐢?AS alias + alias.col 璇硶
                    await cur.execute(
                        "INSERT INTO cockpits (cockpit_id, name, user_id, redis_db, milvus_prefix, theme_color) VALUES "
                        "('cockpit-01', 'Cockpit One', 'user_01', 1, 'cockpit_01', '#4fc3f7'), "
                        "('cockpit-02', 'Cockpit Two', 'user_02', 2, 'cockpit_02', '#66bb6a'), "
                        "('cockpit-03', 'Cockpit Three', 'user_03', 3, 'cockpit_03', '#ab47bc') AS new "
                        "ON DUPLICATE KEY UPDATE name=new.name"
                    )
                    await cur.execute(
                        "INSERT INTO users (user_id, username, cockpit_id, role) VALUES "
                        "('user_01', 'zhang_san', 'cockpit-01', 'cockpit_user'), "
                        "('user_02', 'li_si', 'cockpit-02', 'cockpit_user'), "
                        "('user_03', 'wang_wu', 'cockpit-03', 'cockpit_user'), "
                        "('admin', 'admin', NULL, 'super_admin') AS new "
                        "ON DUPLICATE KEY UPDATE username=new.username"
                    )

                    logger.info("Auto-migrate: all tables verified + default data inserted")
        except Exception as e:
            logger.warning(f"Auto-migrate tables failed (non-fatal): {e}")

    async def _auto_fix_chinese_usernames(self) -> None:
        """鍚姩鏃惰嚜鍔ㄤ慨澶嶄腑鏂囩敤鎴峰悕 鈫?鑻辨枃锛堥伩鍏嶇紪鐮佷贡鐮侊級銆?

        灏嗘暟鎹簱涓凡鏈夌殑涓枃鐢ㄦ埛鍚嶏紙寮犱笁/鏉庡洓/鐜嬩簲/瓒呯骇绠＄悊鍛樼瓑锛?
        鏇存柊涓虹函 ASCII 鑻辨枃鍚嶏紝鍚屾椂淇涓枃搴ц埍鍚嶃€?
        """
        if not self.is_connected:
            return
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    # 淇涓枃鐢ㄦ埛鍚?
                    fixes = [
                        ("user_01", "zhang_san"),
                        ("user_02", "li_si"),
                        ("user_03", "wang_wu"),
                        ("admin", "admin"),
                    ]
                    for user_id, new_name in fixes:
                        await cur.execute(
                            "UPDATE users SET username = %s WHERE user_id = %s AND username != %s",
                            (new_name, user_id, new_name),
                        )
                    # 淇涓枃搴ц埍鍚?
                    cockpit_fixes = [
                        ("cockpit-01", "Cockpit One"),
                        ("cockpit-02", "Cockpit Two"),
                        ("cockpit-03", "Cockpit Three"),
                    ]
                    for cockpit_id, new_name in cockpit_fixes:
                        await cur.execute(
                            "UPDATE cockpits SET name = %s WHERE cockpit_id = %s",
                            (new_name, cockpit_id),
                        )
                    logger.info("Auto-fix: Chinese usernames/cockpit names updated to English")
        except Exception as e:
            logger.warning(f"Auto-fix Chinese usernames failed (non-fatal): {e}")

    async def close(self) -> None:
        """鍏抽棴杩炴帴姹犮€?""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
        self._connected = False
        logger.info("MySQL pool closed")

    @property
    def is_connected(self) -> bool:
        """鏄惁宸茶繛鎺ャ€?""
        return self._connected and self._pool is not None

    def _get_conn(self):
        """浠庤繛鎺ユ睜鑾峰彇杩炴帴涓婁笅鏂囩鐞嗗櫒銆?""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        return self._pool.acquire()

    # ============================================================
    # SubAgent 鏃ュ織
    # ============================================================

    async def insert_subagent_log(
        self,
        cockpit_id: str,
        check_items: dict[str, Any],
        llm_judgment: dict[str, Any] | None = None,
        decision_trace: dict[str, Any] | None = None,
        is_anomaly: bool = False,
    ) -> int | None:
        """鍐欏叆 SubAgent 宸℃鏃ュ織銆?

        Args:
            cockpit_id: 搴ц埍 ID
            check_items: 閲囬泦鐨勭姸鎬佹寚鏍?
            llm_judgment: LLM 鍒ゆ柇缁撴灉
            decision_trace: 鍐崇瓥閾捐矾杩借釜
            is_anomaly: 鏄惁寮傚父

        Returns:
            鎻掑叆鐨勮 ID锛屽け璐ヨ繑鍥?None
        """
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO subagent_logs "
            "(cockpit_id, check_time, check_items, llm_judgment, decision_trace, is_anomaly) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        try:
            # 浣跨敤涓滃叓鍖烘椂闂达紝閬垮厤 Docker 瀹瑰櫒 UTC 鏃跺尯瀵艰嚧鏃堕棿鍋忓樊
            from datetime import timedelta, timezone
            cn_tz = timezone(timedelta(hours=8))
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        datetime.now(cn_tz),
                        json.dumps(check_items, ensure_ascii=False, default=str),
                        json.dumps(llm_judgment, ensure_ascii=False, default=str) if llm_judgment else None,
                        json.dumps(decision_trace, ensure_ascii=False, default=str) if decision_trace else None,
                        is_anomaly,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert subagent log: {e}")
            return None

    # ============================================================
    # MainAgent 鏃ュ織
    # ============================================================

    async def insert_mainagent_log(
        self,
        cockpit_id: str,
        alert_type: str,
        severity: str,
        subagent_judgment: dict[str, Any],
        mainagent_judgment: dict[str, Any],
        action_taken: str,
        alert_time: float | None = None,
        confirm_time: float | None = None,
    ) -> int | None:
        """鍐欏叆 MainAgent 纭鏃ュ織銆?

        Args:
            cockpit_id: 搴ц埍 ID
            alert_type: 鍛婅绫诲瀷
            severity: 涓ラ噸绋嬪害
            subagent_judgment: SubAgent 鍒ゆ柇缁撴灉
            mainagent_judgment: MainAgent 纭缁撴灉
            action_taken: 鎵ц鐨勫姩浣?
            alert_time: 鍛婅鏃堕棿鎴?
            confirm_time: 纭鏃堕棿鎴?

        Returns:
            鎻掑叆鐨勮 ID锛屽け璐ヨ繑鍥?None
        """
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO mainagent_logs "
            "(cockpit_id, alert_time, alert_type, severity, "
            "subagent_judgment, mainagent_judgment, action_taken, confirm_time) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        )
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        datetime.fromtimestamp(alert_time) if alert_time else datetime.now(),
                        alert_type,
                        severity,
                        json.dumps(subagent_judgment, ensure_ascii=False, default=str),
                        json.dumps(mainagent_judgment, ensure_ascii=False, default=str),
                        action_taken,
                        datetime.fromtimestamp(confirm_time) if confirm_time else None,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert mainagent log: {e}")
            return None

    # ============================================================
    # 瀹¤鏃ュ織
    # ============================================================

    async def insert_audit_log(
        self,
        cockpit_id: str,
        user_id: str,
        action: str,
        detail: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> int | None:
        """鍐欏叆瀹¤鏃ュ織銆?

        Args:
            cockpit_id: 搴ц埍 ID
            user_id: 鐢ㄦ埛 ID
            action: 鎿嶄綔绫诲瀷
            detail: 鎿嶄綔璇︽儏
            ip_address: 璇锋眰 IP

        Returns:
            鎻掑叆鐨勮 ID锛屽け璐ヨ繑鍥?None
        """
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO audit_logs "
            "(cockpit_id, user_id, action, detail, ip_address) "
            "VALUES (%s, %s, %s, %s, %s)"
        )
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        user_id,
                        action,
                        json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
                        ip_address,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert audit log: {e}")
            return None

    # ============================================================
    # LLM 鎴愭湰杩借釜
    # ============================================================

    async def insert_llm_cost(
        self,
        cockpit_id: str,
        request_type: str,
        model_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_yuan: float = 0.0,
    ) -> int | None:
        """璁板綍 LLM 璋冪敤鎴愭湰銆?

        Args:
            cockpit_id: 搴ц埍 ID
            request_type: 璇锋眰绫诲瀷锛坈hat/reflection/tool_synthesis锛?
            model_name: 妯″瀷鍚嶇О
            prompt_tokens: 杈撳叆 token 鏁?
            completion_tokens: 杈撳嚭 token 鏁?
            cost_yuan: 鎴愭湰锛堝厓锛?

        Returns:
            鎻掑叆鐨勮 ID锛屽け璐ヨ繑鍥?None
        """
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO llm_cost_tracking "
            "(cockpit_id, request_type, model_name, prompt_tokens, completion_tokens, cost_yuan) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        request_type,
                        model_name,
                        prompt_tokens,
                        completion_tokens,
                        cost_yuan,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert LLM cost: {e}")
            return None

    async def get_llm_cost_summary(
        self, cockpit_id: str | None = None, hours: int = 24
    ) -> dict[str, Any]:
        """鑾峰彇 LLM 鎴愭湰姹囨€汇€?

        Args:
            cockpit_id: 搴ц埍 ID锛堜负绌哄垯鏌ヨ鎵€鏈夛級
            hours: 鏌ヨ鏈€杩戝灏戝皬鏃?

        Returns:
            鎴愭湰姹囨€诲瓧鍏?
        """
        if not self.is_connected:
            return {"total_cost": 0, "total_tokens": 0, "by_cockpit": {}}

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    if cockpit_id:
                        await cur.execute(
                            "SELECT SUM(cost_yuan) as total_cost, "
                            "SUM(prompt_tokens + completion_tokens) as total_tokens, "
                            "COUNT(*) as call_count "
                            "FROM llm_cost_tracking "
                            "WHERE cockpit_id = %s AND created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)",
                            (cockpit_id, hours),
                        )
                    else:
                        await cur.execute(
                            "SELECT SUM(cost_yuan) as total_cost, "
                            "SUM(prompt_tokens + completion_tokens) as total_tokens, "
                            "COUNT(*) as call_count "
                            "FROM llm_cost_tracking "
                            "WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)",
                            (hours,),
                        )
                    summary = await cur.fetchone()

                    # 鎸夊骇鑸卞垎缁?
                    await cur.execute(
                        "SELECT cockpit_id, SUM(cost_yuan) as cost, "
                        "SUM(prompt_tokens + completion_tokens) as tokens "
                        "FROM llm_cost_tracking "
                        "WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR) "
                        "GROUP BY cockpit_id",
                        (hours,),
                    )
                    by_cockpit = {row["cockpit_id"]: {
                        "cost": float(row["cost"] or 0),
                        "tokens": int(row["tokens"] or 0),
                    } for row in await cur.fetchall()}

                    return {
                        "total_cost": float(summary["total_cost"] or 0) if summary else 0,
                        "total_tokens": int(summary["total_tokens"] or 0) if summary else 0,
                        "call_count": int(summary["call_count"] or 0) if summary else 0,
                        "by_cockpit": by_cockpit,
                    }
        except Exception as e:
            logger.error(f"Failed to get LLM cost summary: {e}")
            return {"total_cost": 0, "total_tokens": 0, "by_cockpit": {}}

    # ============================================================
    # 鐢ㄦ埛绠＄悊锛圧BAC锛?
    # ============================================================

    async def list_users(self) -> list[dict[str, Any]]:
        """鍒楀嚭鎵€鏈夌敤鎴枫€?""
        if not self.is_connected:
            return []

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT user_id, username, cockpit_id, role, created_at "
                        "FROM users ORDER BY created_at"
                    )
                    rows = await cur.fetchall()
                    return [
                        {
                            "user_id": r["user_id"],
                            "username": r["username"],
                            "cockpit_id": r["cockpit_id"] or "",
                            "role": r["role"] or "cockpit_user",
                            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        """鏌ヨ鍗曚釜鐢ㄦ埛銆?""
        if not self.is_connected:
            return None

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT user_id, username, cockpit_id, role, password_hash, created_at "
                        "FROM users WHERE user_id = %s",
                        (user_id,),
                    )
                    r = await cur.fetchone()
                    if not r:
                        return None
                    return {
                        "user_id": r["user_id"],
                        "username": r["username"],
                        "cockpit_id": r["cockpit_id"],
                        "role": r["role"],
                        "password_hash": r.get("password_hash"),
                        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                    }
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            return None

    async def create_user(
        self,
        user_id: str,
        username: str,
        cockpit_id: str | None = None,
        role: str = "cockpit_user",
        password_hash: str | None = None,
    ) -> dict[str, Any] | None:
        """鍒涘缓鐢ㄦ埛銆?

        Returns:
            鍒涘缓鐨勭敤鎴峰瓧鍏革紝澶辫触杩斿洖 None
        """
        if not self.is_connected:
            return None

        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO users (user_id, username, cockpit_id, role, password_hash) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (user_id, username, cockpit_id, role, password_hash),
                    )
            return {
                "user_id": user_id,
                "username": username,
                "cockpit_id": cockpit_id,
                "role": role,
                "created_at": datetime.now().isoformat(),
            }
        except aiomysql.IntegrityError as e:
            if e.args[0] == 1062:  # Duplicate entry
                return None
            logger.error(f"Failed to create user: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return None

    async def delete_user(self, user_id: str) -> bool:
        """鍒犻櫎鐢ㄦ埛銆?""
        if not self.is_connected:
            return False

        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete user: {e}")
            return False

    async def update_user_password(self, user_id: str, password_hash: str) -> bool:
        """鏇存柊鐢ㄦ埛瀵嗙爜鍝堝笇銆?""
        if not self.is_connected:
            return False

        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE users SET password_hash = %s WHERE user_id = %s",
                        (password_hash, user_id),
                    )
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update user password: {e}")
            return False

    # ============================================================
    # 瀵硅瘽鍘嗗彶
    # ============================================================

    async def insert_chat_history(
        self,
        cockpit_id: str,
        user_id: str,
        user_input: str,
        assistant_reply: str,
        session_id: str | None = None,
        intent: str | None = None,
        experts_involved: list[str] | None = None,
        latency_ms: float = 0,
        cache_hit: bool = False,
    ) -> int | None:
        """鍐欏叆瀵硅瘽鍘嗗彶銆?""
        if not self.is_connected:
            return None

        sql = (
            "INSERT INTO chat_history "
            "(cockpit_id, user_id, session_id, user_input, assistant_reply, "
            "intent, experts_involved, latency_ms, cache_hit) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, (
                        cockpit_id,
                        user_id,
                        session_id,
                        user_input,
                        assistant_reply,
                        intent,
                        json.dumps(experts_involved) if experts_involved else None,
                        latency_ms,
                        cache_hit,
                    ))
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert chat history: {e}")
            return None

    async def get_chat_history(
        self,
        cockpit_id: str,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """鑾峰彇瀵硅瘽鍘嗗彶銆?""
        if not self.is_connected:
            return []

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    if user_id:
                        await cur.execute(
                            "SELECT * FROM chat_history "
                            "WHERE cockpit_id = %s AND user_id = %s "
                            "ORDER BY created_at DESC LIMIT %s",
                            (cockpit_id, user_id, limit),
                        )
                    else:
                        await cur.execute(
                            "SELECT * FROM chat_history "
                            "WHERE cockpit_id = %s "
                            "ORDER BY created_at DESC LIMIT %s",
                            (cockpit_id, limit),
                        )
                    return [dict(r) for r in await cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get chat history: {e}")
            return []

    # ============================================================
    # 閫氱敤鏌ヨ
    # ============================================================

    async def execute_query(
        self, sql: str, params: tuple = ()
    ) -> list[dict[str, Any]]:
        """鎵ц鏌ヨ骞惰繑鍥炵粨鏋溿€?""
        if not self.is_connected:
            return []

        try:
            async with self._get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql, params)
                    return [dict(r) for r in await cur.fetchall()]
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

    async def execute_update(
        self, sql: str, params: tuple = ()
    ) -> int:
        """鎵ц INSERT/UPDATE/DELETE 骞惰繑鍥炲彈褰卞搷琛屾暟銆?""
        if not self.is_connected:
            return 0

        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, params)
                    return cur.rowcount
        except Exception as e:
            logger.error(f"Update failed: {e}")
            return 0

    # ============================================================
    # 鐢ㄦ埛涔犳儻
    # ============================================================

    async def record_user_habit(
        self, user_id: str, cockpit_id: str, habit_key: str, habit_value: str = ""
    ) -> None:
        """璁板綍鐢ㄦ埛涔犳儻锛圲PSERT锛屽凡瀛樺湪鍒?hit_count+1锛夈€?

        Args:
            user_id: 鐢ㄦ埛 ID
            cockpit_id: 搴ц埍 ID
            habit_key: 涔犳儻閿悕锛堝 preferred_temp銆乫avorite_music锛?
            habit_value: 涔犳儻鍊?
        """
        if not self.is_connected:
            return
        try:
            async with self._get_conn() as conn:
                async with conn.cursor() as cur:
                    # MySQL 8.0+ 寮冪敤浜?VALUES(col) 璇硶锛屾敼鐢?AS new + new.col 璇硶
                    # ON DUPLICATE KEY UPDATE 涓?hit_count 蹇呴』鐢ㄨ〃鍚嶉檺瀹氾紝
                    # 鍚﹀垯 MySQL 鏃犳硶鍖哄垎鏄?existing 琛岃繕鏄?new 琛岀殑鍒楋紙ambiguous 閿欒锛?
                    await cur.execute(
                        "INSERT INTO user_habits "
                        "(user_id, cockpit_id, habit_key, habit_value, hit_count, last_used_at) "
                        "VALUES (%s, %s, %s, %s, 1, NOW()) AS new "
                        "ON DUPLICATE KEY UPDATE "
                        "habit_value=new.habit_value, "
                        "user_habits.hit_count=user_habits.hit_count+1, last_used_at=NOW()",
                        (user_id, cockpit_id, habit_key, habit_value),
                    )
        except Exception as e:
            logger.error(f"Failed to record user habit: {e}")

    async def get_user_habits(
        self, user_id: str, cockpit_id: str = ""
    ) -> list[dict[str, Any]]:
        """鑾峰彇鐢ㄦ埛涔犳儻鍒楄〃銆?""
        if not self.is_connected:
            return []
        try:
            if cockpit_id:
                sql = "SELECT * FROM user_habits WHERE user_id=%s AND cockpit_id=%s ORDER BY hit_count DESC"
                params = (user_id, cockpit_id)
            else:
                sql = "SELECT * FROM user_habits WHERE user_id=%s ORDER BY hit_count DESC"
                params = (user_id,)
            return await self.execute_query(sql, params)
        except Exception as e:
            logger.error(f"Failed to get user habits: {e}")
            return []


# 鍏ㄥ眬鍗曚緥
_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """鑾峰彇鏁版嵁搴撶鐞嗗櫒鍏ㄥ眬鍗曚緥銆?""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
