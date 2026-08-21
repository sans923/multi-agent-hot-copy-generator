"""数据库持久化的 Agent 任务执行队列。"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.database import Base


class TaskExecutionJob(Base):
    __tablename__ = "task_execution_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_type = Column(String(20), nullable=False)
    dedupe_key = Column(String(160), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    locked_at = Column(DateTime, nullable=True, index=True)
    worker_id = Column(String(120), nullable=True)
    lease_token = Column(String(36), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_task_execution_job_dedupe_key"),
        Index(
            "ix_task_execution_ready",
            "status",
            "available_at",
            "created_at",
        ),
    )
