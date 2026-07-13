"""
编排审计日志表（orchestration_audit_logs）
==========================================
全链路审计：编排阶段、Skill、LLM、验证、Judge、人工介入等每一步落库，
保证任务执行「有迹可循」。
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON, Index
from sqlalchemy.orm import relationship

from app.database import Base


class OrchestrationAuditLog(Base):
    __tablename__ = "orchestration_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="审计日志ID")

    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联任务ID",
    )

    # orchestration | skill | llm | verify | judge | human | system | stage
    step_type = Column(String(30), nullable=False, index=True, comment="步骤类型")

    step_name = Column(String(100), nullable=False, index=True, comment="步骤名称")

    agent_name = Column(String(50), nullable=True, comment="Agent名称")

    # 任务内顺序号（从 1 递增，便于时间线展示）
    sequence_no = Column(Integer, nullable=False, default=1, comment="任务内顺序号")

    input_summary = Column(JSON, nullable=True, comment="输入摘要")
    output_summary = Column(JSON, nullable=True, comment="输出摘要")

    status = Column(
        String(20),
        nullable=False,
        default="success",
        comment="success|failed|retry|skipped",
    )

    failure_level = Column(String(20), nullable=True, comment="retry|local|global|human")

    duration_ms = Column(Float, nullable=True, comment="耗时毫秒")
    error_message = Column(Text, nullable=True, comment="错误信息")

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="记录时间",
    )

    task = relationship("Task", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_task_seq", "task_id", "sequence_no"),
        Index("ix_audit_task_created", "task_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<OrchestrationAuditLog id={self.id} task={self.task_id} "
            f"type={self.step_type} name={self.step_name} status={self.status}>"
        )
