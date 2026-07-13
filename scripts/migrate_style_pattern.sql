-- 头条长文互动量字段 + 风格卡表（已有库执行一次）
-- mysql -u copygen -p copy_generator < scripts/migrate_style_pattern.sql

USE copy_generator;

ALTER TABLE toutiao_reference
  ADD COLUMN IF NOT EXISTS like_count BIGINT NOT NULL DEFAULT 0 COMMENT '点赞数',
  ADD COLUMN IF NOT EXISTS read_count BIGINT NOT NULL DEFAULT 0 COMMENT '阅读数',
  ADD COLUMN IF NOT EXISTS comment_count BIGINT NOT NULL DEFAULT 0 COMMENT '评论数',
  ADD COLUMN IF NOT EXISTS publish_time DATETIME NULL COMMENT '发布时间';

CREATE INDEX IF NOT EXISTS idx_toutiao_ref_like_count ON toutiao_reference (like_count);

CREATE TABLE IF NOT EXISTS style_cards (
  id INT AUTO_INCREMENT PRIMARY KEY,
  topic_cluster VARCHAR(100) NOT NULL,
  platform VARCHAR(30) NOT NULL DEFAULT 'toutiao',
  pattern_json JSON NOT NULL,
  avg_like_count INT DEFAULT 0,
  source_article_ids JSON NULL,
  confidence FLOAT DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_style_card_topic_platform (topic_cluster, platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
