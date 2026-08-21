-- 真实内容生产 P0：任务三域状态、生成快照和反馈版本。
-- MySQL 8，可重复执行；SQLite 测试库由 SQLAlchemy create_all 建表。

ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS execution_status VARCHAR(30) NOT NULL DEFAULT 'queued',
  ADD COLUMN IF NOT EXISTS content_status VARCHAR(30) NOT NULL DEFAULT 'brief_missing',
  ADD COLUMN IF NOT EXISTS publication_status VARCHAR(30) NOT NULL DEFAULT 'not_prepared',
  ADD COLUMN IF NOT EXISTS status_reason TEXT NULL,
  ADD COLUMN IF NOT EXISTS status_updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE copies
  ADD COLUMN IF NOT EXISTS parent_copy_id INT NULL,
  ADD COLUMN IF NOT EXISTS applied_style_snapshot JSON NULL,
  ADD COLUMN IF NOT EXISTS knowledge_citations JSON NULL,
  ADD COLUMN IF NOT EXISTS change_summary JSON NULL,
  ADD COLUMN IF NOT EXISTS user_edited TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS adopted_at DATETIME NULL;

ALTER TABLE memory_feedback
  ADD COLUMN IF NOT EXISTS result_copy_id INT NULL;

SET @index_sql := IF(
  (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'tasks' AND index_name = 'ix_tasks_execution_status') = 0,
  'CREATE INDEX ix_tasks_execution_status ON tasks (execution_status)', 'SELECT 1'
);
PREPARE index_statement FROM @index_sql; EXECUTE index_statement; DEALLOCATE PREPARE index_statement;

SET @index_sql := IF(
  (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'tasks' AND index_name = 'ix_tasks_content_status') = 0,
  'CREATE INDEX ix_tasks_content_status ON tasks (content_status)', 'SELECT 1'
);
PREPARE index_statement FROM @index_sql; EXECUTE index_statement; DEALLOCATE PREPARE index_statement;

SET @index_sql := IF(
  (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'tasks' AND index_name = 'ix_tasks_publication_status') = 0,
  'CREATE INDEX ix_tasks_publication_status ON tasks (publication_status)', 'SELECT 1'
);
PREPARE index_statement FROM @index_sql; EXECUTE index_statement; DEALLOCATE PREPARE index_statement;

SET @index_sql := IF(
  (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'copies' AND index_name = 'ix_copies_parent_copy_id') = 0,
  'CREATE INDEX ix_copies_parent_copy_id ON copies (parent_copy_id)', 'SELECT 1'
);
PREPARE index_statement FROM @index_sql; EXECUTE index_statement; DEALLOCATE PREPARE index_statement;

SET @index_sql := IF(
  (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'memory_feedback' AND index_name = 'ix_memory_feedback_result_copy_id') = 0,
  'CREATE INDEX ix_memory_feedback_result_copy_id ON memory_feedback (result_copy_id)', 'SELECT 1'
);
PREPARE index_statement FROM @index_sql; EXECUTE index_statement; DEALLOCATE PREPARE index_statement;
