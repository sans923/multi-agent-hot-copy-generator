"""长期记忆权威数据：显式偏好、反馈、版本化条目和风格卡历史。"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    preferences = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class MemoryFeedback(Base):
    __tablename__ = "memory_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    copy_id = Column(
        Integer,
        ForeignKey("copies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String(30), nullable=False)
    rating = Column(Integer, nullable=False, default=0)
    comment = Column(Text, nullable=True)
    metrics = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("rating >= -1 AND rating <= 1", name="ck_memory_feedback_rating"),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_memory_feedback_user_idempotency",
        ),
        Index("ix_memory_feedback_user_created", "user_id", "created_at"),
    )


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    memory_type = Column(String(40), nullable=False, index=True)
    scope_id = Column(String(100), nullable=False, default="default")
    source_type = Column(String(40), nullable=False)
    source_id = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    content_json = Column(JSON, nullable=True)
    content_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="candidate", index=True)
    schema_version = Column(Integer, nullable=False, default=1)
    version = Column(Integer, nullable=False, default=1)
    confidence = Column(Float, nullable=False, default=1.0)
    quality_score = Column(Float, nullable=False, default=0.0)
    supersedes_id = Column(
        Integer,
        ForeignKey("memory_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "memory_type",
            "scope_id",
            "source_type",
            "source_id",
            "version",
            name="uq_memory_item_version",
        ),
        Index("ix_memory_scope_status", "user_id", "memory_type", "scope_id", "status"),
    )


class StyleCardVersion(Base):
    __tablename__ = "style_card_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    style_card_id = Column(
        Integer,
        ForeignKey("style_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    pattern_json = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="candidate", index=True)
    schema_version = Column(Integer, nullable=False, default=1)
    source_article_ids = Column(JSON, nullable=False, default=list)
    confidence = Column(Float, nullable=False, default=0.0)
    supersedes_id = Column(
        Integer,
        ForeignKey("style_card_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("style_card_id", "version", name="uq_style_card_version"),
        Index("ix_style_card_version_status", "style_card_id", "status"),
    )
