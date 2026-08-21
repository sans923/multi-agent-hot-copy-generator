-- 记忆索引任务租约字段（可重复执行）
-- 全新数据库由 SQLAlchemy create_all 建列；旧库由 setup_mysql.py 执行本迁移。

SET @locked_at_column_exists := (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'memory_index_jobs'
    AND column_name = 'locked_at'
);
SET @locked_at_column_sql := IF(
  @locked_at_column_exists = 0,
  'ALTER TABLE memory_index_jobs ADD COLUMN locked_at DATETIME NULL AFTER attempts',
  'SELECT 1'
);
PREPARE locked_at_column_statement FROM @locked_at_column_sql;
EXECUTE locked_at_column_statement;
DEALLOCATE PREPARE locked_at_column_statement;

SET @locked_at_index_exists := (
  SELECT COUNT(*)
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'memory_index_jobs'
    AND index_name = 'ix_memory_index_jobs_locked_at'
);
SET @locked_at_index_sql := IF(
  @locked_at_index_exists = 0,
  'CREATE INDEX ix_memory_index_jobs_locked_at ON memory_index_jobs (locked_at)',
  'SELECT 1'
);
PREPARE locked_at_index_statement FROM @locked_at_index_sql;
EXECUTE locked_at_index_statement;
DEALLOCATE PREPARE locked_at_index_statement;
