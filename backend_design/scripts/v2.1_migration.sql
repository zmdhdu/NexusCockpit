-- ============================================================
-- NexusCockpit v2.1 数据库迁移脚本
-- 执行方式: mysql -u root -p < v2.1_migration.sql
--
-- 本脚本包含两部分:
-- 1. v2.1 新增表（CREATE TABLE IF NOT EXISTS）
-- 2. v2.0 遗留表安全升级（ALTER TABLE 添加 cockpit_id 列）
-- ============================================================

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS nexus_cockpit CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE nexus_cockpit;

-- ============================================================
-- Part 1: v2.1 新增表
-- ============================================================

-- ============================================================
-- 座舱表
-- ============================================================
CREATE TABLE IF NOT EXISTS cockpits (
    cockpit_id        VARCHAR(32) PRIMARY KEY,
    name              VARCHAR(64) NOT NULL,
    user_id           VARCHAR(64) NOT NULL,
    vehicle_adapter   VARCHAR(32) DEFAULT 'mock',
    redis_db          INT DEFAULT 0,
    milvus_prefix     VARCHAR(64) DEFAULT '',
    theme_color       VARCHAR(16) DEFAULT '#4fc3f7',
    is_active         BOOLEAN DEFAULT TRUE,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 用户表（v2.1 RBAC 四级角色）
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id           VARCHAR(64) PRIMARY KEY,
    username          VARCHAR(64) NOT NULL,
    password_hash     VARCHAR(256),
    cockpit_id        VARCHAR(32),
    role              ENUM('super_admin', 'cockpit_admin', 'cockpit_user', 'cockpit_viewer')
                      DEFAULT 'cockpit_user',
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cockpit_id) REFERENCES cockpits(cockpit_id) ON DELETE SET NULL,
    INDEX idx_cockpit (cockpit_id),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 对话历史表（v2.1 新增，支持多租户隔离）
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_history (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    cockpit_id        VARCHAR(32) NOT NULL,
    user_id           VARCHAR(64) NOT NULL,
    session_id        VARCHAR(128),
    user_input        TEXT NOT NULL,
    assistant_reply   TEXT,
    intent            VARCHAR(64),
    experts_involved  JSON,
    latency_ms        FLOAT DEFAULT 0,
    cache_hit         BOOLEAN DEFAULT FALSE,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cockpit_time (cockpit_id, created_at),
    INDEX idx_user_time (user_id, created_at),
    INDEX idx_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 座舱使用统计表（数据中台用，每分钟聚合）
-- ============================================================
CREATE TABLE IF NOT EXISTS cockpit_stats (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    cockpit_id        VARCHAR(32) NOT NULL,
    stat_time         DATETIME NOT NULL,
    chat_count        INT DEFAULT 0,
    vehicle_cmd_count INT DEFAULT 0,
    cache_hits        INT DEFAULT 0,
    cache_misses      INT DEFAULT 0,
    avg_latency_ms    FLOAT DEFAULT 0,
    p95_latency_ms    FLOAT DEFAULT 0,
    error_count       INT DEFAULT 0,
    INDEX idx_cockpit_time (cockpit_id, stat_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- SubAgent 巡检日志
-- ============================================================
CREATE TABLE IF NOT EXISTS subagent_logs (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    cockpit_id        VARCHAR(32) NOT NULL,
    check_time        DATETIME NOT NULL,
    check_items       JSON,
    llm_judgment      JSON,
    decision_trace    JSON,
    is_anomaly        BOOLEAN DEFAULT FALSE,
    INDEX idx_cockpit_time (cockpit_id, check_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- MainAgent 确认日志
-- ============================================================
CREATE TABLE IF NOT EXISTS mainagent_logs (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    cockpit_id        VARCHAR(32) NOT NULL,
    alert_time        DATETIME NOT NULL,
    alert_type        VARCHAR(64),
    severity          VARCHAR(16),
    subagent_judgment JSON,
    mainagent_judgment JSON,
    action_taken      VARCHAR(32),
    confirm_time      DATETIME,
    INDEX idx_cockpit_time (cockpit_id, alert_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 审计日志表
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    cockpit_id        VARCHAR(32) NOT NULL,
    user_id           VARCHAR(64) NOT NULL,
    action            VARCHAR(64) NOT NULL,
    detail            JSON,
    ip_address        VARCHAR(45),
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cockpit_time (cockpit_id, created_at),
    INDEX idx_user_time (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 用户反馈表
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_feedback (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    cockpit_id        VARCHAR(32) NOT NULL,
    user_id           VARCHAR(64) NOT NULL,
    mainagent_log_id  BIGINT,
    feedback          ENUM('positive', 'negative') NOT NULL,
    comment           TEXT,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cockpit_time (cockpit_id, created_at),
    FOREIGN KEY (mainagent_log_id) REFERENCES mainagent_logs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- LLM 成本追踪表
-- ============================================================
CREATE TABLE IF NOT EXISTS llm_cost_tracking (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    cockpit_id        VARCHAR(32) NOT NULL,
    request_type      VARCHAR(32) NOT NULL,
    model_name        VARCHAR(64) NOT NULL,
    prompt_tokens     INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    cost_yuan         DECIMAL(10, 6) DEFAULT 0,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cockpit_time (cockpit_id, created_at),
    INDEX idx_type_time (request_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 声纹注册记录表（v2.1 新增，跟踪声纹注册状态）
-- ============================================================
CREATE TABLE IF NOT EXISTS voiceprint_enrollments (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    cockpit_id        VARCHAR(32) NOT NULL,
    user_id           VARCHAR(64) NOT NULL,
    enroll_count      INT DEFAULT 0,
    required_count    INT DEFAULT 3,
    is_completed      BOOLEAN DEFAULT FALSE,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_cockpit_user (cockpit_id, user_id),
    INDEX idx_cockpit (cockpit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Part 2: v2.0 遗留表安全升级（ALTER TABLE 添加 cockpit_id）
-- 使用存储过程实现 "ADD COLUMN IF NOT EXISTS" 语义
-- ============================================================

-- 安全添加列的存储过程
DROP PROCEDURE IF EXISTS safe_add_column;
DELIMITER //
CREATE PROCEDURE safe_add_column(
    IN tbl VARCHAR(64),
    IN col VARCHAR(64),
    IN col_def VARCHAR(256)
)
BEGIN
    SET @ddl = CONCAT('ALTER TABLE ', tbl, ' ADD COLUMN ', col, ' ', col_def);
    SET @check = CONCAT('SELECT COUNT(*) INTO @exists FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ''', tbl, ''' AND column_name = ''', col, '''');
    PREPARE stmt FROM @check;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
    IF @exists = 0 THEN
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- 安全添加索引的存储过程
DROP PROCEDURE IF EXISTS safe_add_index;
DELIMITER //
CREATE PROCEDURE safe_add_index(
    IN tbl VARCHAR(64),
    IN idx_name VARCHAR(64),
    IN idx_cols VARCHAR(256)
)
BEGIN
    SET @check = CONCAT('SELECT COUNT(*) INTO @exists FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = ''', tbl, ''' AND index_name = ''', idx_name, '''');
    PREPARE stmt FROM @check;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
    IF @exists = 0 THEN
        SET @ddl = CONCAT('ALTER TABLE ', tbl, ' ADD INDEX ', idx_name, ' (', idx_cols, ')');
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- --- 为 v2.0 遗留表添加 cockpit_id 列（如果表存在且缺少该列）---

-- users 表（v2.0 可能已存在但无 cockpit_id）
CALL safe_add_column('users', 'cockpit_id', "VARCHAR(32) DEFAULT NULL");
CALL safe_add_index('users', 'idx_cockpit', 'cockpit_id');

-- users 表添加 role 列（v2.0 可能没有 RBAC 角色）
CALL safe_add_column('users', 'role', "ENUM('super_admin', 'cockpit_admin', 'cockpit_user', 'cockpit_viewer') DEFAULT 'cockpit_user'");
CALL safe_add_index('users', 'idx_role', 'role');

-- chat_history 表（如果 v2.0 已有但无 cockpit_id）
CALL safe_add_column('chat_history', 'cockpit_id', "VARCHAR(32) NOT NULL DEFAULT 'cockpit-01'");
CALL safe_add_index('chat_history', 'idx_cockpit_time', 'cockpit_id, created_at');

-- 清理存储过程
DROP PROCEDURE IF EXISTS safe_add_column;
DROP PROCEDURE IF EXISTS safe_add_index;

-- ============================================================
-- Part 3: 插入默认数据
-- ============================================================

-- 3 个默认座舱
INSERT INTO cockpits (cockpit_id, name, user_id, redis_db, milvus_prefix, theme_color) VALUES
    ('cockpit-01', 'Cockpit One', 'user_01', 1, 'cockpit_01', '#4fc3f7'),
    ('cockpit-02', 'Cockpit Two', 'user_02', 2, 'cockpit_02', '#66bb6a'),
    ('cockpit-03', 'Cockpit Three', 'user_03', 3, 'cockpit_03', '#ab47bc')
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- 默认用户（密码为空，Demo 模式）
INSERT INTO users (user_id, username, cockpit_id, role) VALUES
    ('user_01', 'zhang_san', 'cockpit-01', 'cockpit_user'),
    ('user_02', 'li_si', 'cockpit-02', 'cockpit_user'),
    ('user_03', 'wang_wu', 'cockpit-03', 'cockpit_user'),
    ('admin', 'admin', NULL, 'super_admin')
ON DUPLICATE KEY UPDATE username=VALUES(username);

-- 完成
SELECT 'v2.1 migration completed successfully' AS message;

-- ============================================================
-- Part 4: v2.1 补充表 — 聊天日志 + 用户习惯
-- ============================================================

-- 聊天日志表（用户隐私数据，管理员不可查看内容）
CREATE TABLE IF NOT EXISTS chat_logs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    cockpit_id      VARCHAR(32) NOT NULL,
    user_id         VARCHAR(64) NOT NULL,
    user_input      TEXT NOT NULL,
    assistant_response TEXT,
    intent          VARCHAR(128) DEFAULT '',
    action          VARCHAR(128) DEFAULT '',
    latency_ms      FLOAT DEFAULT 0,
    cache_hit       BOOLEAN DEFAULT FALSE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cockpit_user (cockpit_id, user_id),
    INDEX idx_cockpit_time (cockpit_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户习惯表（存储用户偏好，跨座舱不丢失）
CREATE TABLE IF NOT EXISTS user_habits (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    cockpit_id      VARCHAR(32) NOT NULL,
    habit_key       VARCHAR(128) NOT NULL,
    habit_value     TEXT,
    hit_count       INT DEFAULT 1,
    last_used_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_cockpit_habit (user_id, cockpit_id, habit_key),
    INDEX idx_user (user_id),
    INDEX idx_cockpit (cockpit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Fix: 修复已有中文用户名 → 英文（避免编码乱码）
-- ============================================================
UPDATE users SET username = 'zhang_san'    WHERE user_id = 'user_01' AND username != 'zhang_san';
UPDATE users SET username = 'li_si'        WHERE user_id = 'user_02' AND username != 'li_si';
UPDATE users SET username = 'wang_wu'      WHERE user_id = 'user_03' AND username != 'wang_wu';
UPDATE users SET username = 'admin'        WHERE user_id = 'admin'   AND username != 'admin';

-- 修复已有中文座舱名
UPDATE cockpits SET name = 'Cockpit One'   WHERE cockpit_id = 'cockpit-01';
UPDATE cockpits SET name = 'Cockpit Two'   WHERE cockpit_id = 'cockpit-02';
UPDATE cockpits SET name = 'Cockpit Three' WHERE cockpit_id = 'cockpit-03';

-- ============================================================
-- Part 5: v2.2.2 多会话聊天支持
-- ============================================================

-- 会话表
CREATE TABLE IF NOT EXISTS chat_sessions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(128) NOT NULL UNIQUE,
    cockpit_id      VARCHAR(32) NOT NULL,
    user_id         VARCHAR(64) NOT NULL,
    title           VARCHAR(128) DEFAULT '新对话',
    message_count   INT DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_message_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_cockpit_time (cockpit_id, last_message_at),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 重新创建存储过程（Part 2 中已删除）
DROP PROCEDURE IF EXISTS safe_add_column;
DELIMITER //
CREATE PROCEDURE safe_add_column(
    IN tbl VARCHAR(64),
    IN col VARCHAR(64),
    IN col_def VARCHAR(256)
)
BEGIN
    SET @ddl = CONCAT('ALTER TABLE ', tbl, ' ADD COLUMN ', col, ' ', col_def);
    SET @check = CONCAT('SELECT COUNT(*) INTO @exists FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ''', tbl, ''' AND column_name = ''', col, '''');
    PREPARE stmt FROM @check;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
    IF @exists = 0 THEN
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

DROP PROCEDURE IF EXISTS safe_add_index;
DELIMITER //
CREATE PROCEDURE safe_add_index(
    IN tbl VARCHAR(64),
    IN idx_name VARCHAR(64),
    IN idx_cols VARCHAR(256)
)
BEGIN
    SET @check = CONCAT('SELECT COUNT(*) INTO @exists FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = ''', tbl, ''' AND index_name = ''', idx_name, '''');
    PREPARE stmt FROM @check;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
    IF @exists = 0 THEN
        SET @ddl = CONCAT('ALTER TABLE ', tbl, ' ADD INDEX ', idx_name, ' (', idx_cols, ')');
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- 为 chat_logs 表添加 session_id 列（如果不存在）
CALL safe_add_column('chat_logs', 'session_id', "VARCHAR(128) DEFAULT ''");
CALL safe_add_index('chat_logs', 'idx_session', 'session_id');

-- 清理存储过程
DROP PROCEDURE IF EXISTS safe_add_column;
DROP PROCEDURE IF EXISTS safe_add_index;


