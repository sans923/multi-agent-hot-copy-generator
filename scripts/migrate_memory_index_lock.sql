-- 记忆索引任务租约字段
-- 仅用于从旧版 memory_index_jobs 表升级；全新数据库由 SQLAlchemy create_all 建列。

ALTER TABLE memory_index_jobs
  ADD COLUMN locked_at DATETIME NULL AFTER attempts;

CREATE INDEX ix_memory_index_jobs_locked_at
  ON memory_index_jobs (locked_at);
