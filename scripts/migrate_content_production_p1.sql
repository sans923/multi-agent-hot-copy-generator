-- 真实内容生产 P1：内容简报、分层风格卡与受治理知识库。
-- MySQL 8，可重复执行；SQLite 测试库由 SQLAlchemy create_all 建表。

ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS content_brief JSON NULL,
  ADD COLUMN IF NOT EXISTS brief_completeness FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS brief_missing_fields JSON NULL;

ALTER TABLE style_cards
  ADD COLUMN IF NOT EXISTS owner_id INT NULL,
  ADD COLUMN IF NOT EXISTS layer VARCHAR(30) NOT NULL DEFAULT 'account',
  ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 30,
  ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS schema_version INT NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS knowledge_sources (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NULL,
  knowledge_type VARCHAR(40) NOT NULL,
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  source_uri VARCHAR(1000) NULL,
  content_hash VARCHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  version INT NOT NULL DEFAULT 1,
  metadata_json JSON NOT NULL,
  valid_from DATETIME NULL,
  valid_to DATETIME NULL,
  index_status VARCHAR(20) NOT NULL DEFAULT 'pending',
  supersedes_id INT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_knowledge_source_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_knowledge_source_previous FOREIGN KEY (supersedes_id) REFERENCES knowledge_sources(id) ON DELETE SET NULL,
  CONSTRAINT uq_knowledge_source_version UNIQUE (user_id, knowledge_type, title, version),
  INDEX ix_knowledge_source_user_id (user_id),
  INDEX ix_knowledge_source_type (knowledge_type),
  INDEX ix_knowledge_source_status (status),
  INDEX ix_knowledge_source_hash (content_hash),
  INDEX ix_knowledge_scope_status (user_id, knowledge_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id INT NOT NULL AUTO_INCREMENT,
  source_id INT NOT NULL,
  chunk_key VARCHAR(100) NOT NULL,
  content TEXT NOT NULL,
  content_hash VARCHAR(64) NOT NULL,
  metadata_json JSON NOT NULL,
  token_estimate INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_knowledge_chunk_source FOREIGN KEY (source_id) REFERENCES knowledge_sources(id) ON DELETE CASCADE,
  CONSTRAINT uq_knowledge_chunk_key UNIQUE (source_id, chunk_key),
  INDEX ix_knowledge_chunk_source_id (source_id),
  INDEX ix_knowledge_chunk_hash (content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @index_sql := IF(
  (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'style_cards' AND index_name = 'ix_style_cards_owner_id') = 0,
  'CREATE INDEX ix_style_cards_owner_id ON style_cards (owner_id)', 'SELECT 1'
);
PREPARE index_statement FROM @index_sql; EXECUTE index_statement; DEALLOCATE PREPARE index_statement;

SET @fk_sql := IF(
  (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema = DATABASE() AND table_name = 'style_cards' AND constraint_name = 'fk_style_card_owner') = 0,
  'ALTER TABLE style_cards ADD CONSTRAINT fk_style_card_owner FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE', 'SELECT 1'
);
PREPARE fk_statement FROM @fk_sql; EXECUTE fk_statement; DEALLOCATE PREPARE fk_statement;
