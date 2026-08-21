"""记忆向量索引 Outbox：业务写入成功后可异步、幂等地建立派生索引。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from app.database import Base


class MemoryIndexJob(Base):
    __tablename__ = "memory_index_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String(30), nullable=False, default="upsert_copy")
    entity_id = Column(Integer, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    locked_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("job_type", "entity_id", name="uq_memory_index_job_entity"),
        Index("ix_memory_index_status_created", "status", "created_at"),
    )
