-- Phase 3: 全链路编排审计日志表

CREATE TABLE IF NOT EXISTS orchestration_audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id INT NOT NULL,
    step_type VARCHAR(30) NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    agent_name VARCHAR(50) NULL,
    sequence_no INT NOT NULL DEFAULT 1,
    input_summary JSON NULL,
    output_summary JSON NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'success',
    failure_level VARCHAR(20) NULL,
    duration_ms FLOAT NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_orchestration_audit_logs_task_id (task_id),
    INDEX ix_audit_task_seq (task_id, sequence_no),
    INDEX ix_audit_task_created (task_id, created_at),
    CONSTRAINT fk_audit_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
) COMMENT='编排全链路审计日志';
