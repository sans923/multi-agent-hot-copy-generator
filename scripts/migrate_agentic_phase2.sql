-- Phase 2: Agentic 编排元数据 + 人工介入状态
-- 在已有 MySQL 库执行；SQLite 测试库由 create_all 自动建列

ALTER TABLE tasks
  ADD COLUMN orchestration_meta JSON NULL COMMENT '编排元数据' AFTER error_message;

-- 若使用 MySQL ENUM，需扩展 status 枚举（SQLite 无此限制）
-- ALTER TABLE tasks MODIFY COLUMN status ENUM(
--   'pending','processing','awaiting_human','completed','failed'
-- ) NOT NULL DEFAULT 'pending';
