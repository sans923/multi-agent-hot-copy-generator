-- 真实内容生产 P2：发布结果与效果指标真源。
-- MySQL 8，可重复执行；SQLite 测试库由 SQLAlchemy create_all 建表。

CREATE TABLE IF NOT EXISTS publication_records (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  task_id INT NOT NULL,
  copy_id INT NOT NULL,
  platform VARCHAR(30) NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'submitted',
  external_id VARCHAR(255) NULL,
  url VARCHAR(1000) NULL,
  metrics JSON NOT NULL,
  idempotency_key VARCHAR(100) NOT NULL,
  submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  published_at DATETIME NULL,
  metrics_updated_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_publication_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_publication_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
  CONSTRAINT fk_publication_copy FOREIGN KEY (copy_id) REFERENCES copies(id) ON DELETE CASCADE,
  CONSTRAINT uq_publication_user_idempotency UNIQUE (user_id, idempotency_key),
  INDEX ix_publication_user_id (user_id),
  INDEX ix_publication_task_id (task_id),
  INDEX ix_publication_copy_id (copy_id),
  INDEX ix_publication_status (status),
  INDEX ix_publication_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
