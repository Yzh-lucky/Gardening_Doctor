-- AI 园艺医生 · 本地一键初始化
-- 用法（PowerShell）：mysql -u root -p < backend/scripts/init_db.sql
-- 与 alembic/versions/0001_init.py 等价：二选一即可，别同时用（会把 alembic 版本表搞乱）
-- 说明：diagnosis_records 比准备文档 3.5.2 多一列 deleted_at，用于软删除

CREATE DATABASE IF NOT EXISTS gardening_doctor
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE gardening_doctor;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  openid        VARCHAR(64)  NOT NULL COMMENT '微信 openid',
  unionid       VARCHAR(64)  DEFAULT NULL,
  nickname      VARCHAR(64)  DEFAULT NULL,
  avatar_url    VARCHAR(512) DEFAULT NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_login_at DATETIME     DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_openid (openid)
) ENGINE=InnoDB COMMENT='用户';

-- 诊断记录表
CREATE TABLE IF NOT EXISTS diagnosis_records (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id        BIGINT UNSIGNED NOT NULL,
  image_urls     JSON           NOT NULL COMMENT '图片地址数组',
  image_hash     CHAR(64)       DEFAULT NULL COMMENT '首图 sha256，用于缓存命中',
  status         VARCHAR(16)    NOT NULL DEFAULT 'created' COMMENT 'created/recognizing/success/degraded/failed/corrected',
  prompt_version VARCHAR(16)    DEFAULT NULL,
  model_name     VARCHAR(64)    DEFAULT NULL,
  disease_name   VARCHAR(64)    DEFAULT NULL,
  confidence     DECIMAL(4,3)   DEFAULT NULL,
  result_json    JSON           DEFAULT NULL COMMENT '结构化识别结果',
  cost_tokens    INT            NOT NULL DEFAULT 0,
  latency_ms     INT            NOT NULL DEFAULT 0,
  created_at     DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  deleted_at     DATETIME       DEFAULT NULL COMMENT '软删除时间',
  PRIMARY KEY (id),
  KEY idx_user_time (user_id, created_at),
  KEY idx_hash (image_hash)
) ENGINE=InnoDB COMMENT='诊断记录';

-- 病虫害知识库
CREATE TABLE IF NOT EXISTS diseases (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(64)  NOT NULL,
  aliases       VARCHAR(255) DEFAULT NULL,
  category      VARCHAR(32)  DEFAULT NULL COMMENT '真菌性/细菌性/病毒性/虫害/生理性',
  symptoms      TEXT,
  causes        TEXT,
  plan_l1       JSON COMMENT '家庭安全处置',
  plan_l2       JSON COMMENT '低毒合规处置',
  plan_l3       JSON COMMENT '专业干预',
  safety_notes  TEXT,
  confused_with VARCHAR(255) DEFAULT NULL,
  version       INT          NOT NULL DEFAULT 1,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_name (name),
  KEY idx_category (category)
) ENGINE=InnoDB COMMENT='病虫害知识库';

-- 反馈表
CREATE TABLE IF NOT EXISTS feedbacks (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  record_id    BIGINT UNSIGNED NOT NULL,
  user_id      BIGINT UNSIGNED NOT NULL,
  type         VARCHAR(16) NOT NULL COMMENT 'like/dislike/wrong',
  correct_name VARCHAR(64) DEFAULT NULL,
  comment      TEXT,
  created_at   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_record (record_id)
) ENGINE=InnoDB COMMENT='用户反馈';

-- 额度表
CREATE TABLE IF NOT EXISTS quota_usages (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id     BIGINT UNSIGNED NOT NULL,
  stat_date   DATE NOT NULL,
  used_count  INT  NOT NULL DEFAULT 0,
  limit_count INT  NOT NULL DEFAULT 10,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_date (user_id, stat_date)
) ENGINE=InnoDB COMMENT='每日额度';

-- 管理员
CREATE TABLE IF NOT EXISTS admins (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username      VARCHAR(32) NOT NULL,
  password_hash VARCHAR(128) NOT NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_username (username)
) ENGINE=InnoDB COMMENT='后台管理员';
