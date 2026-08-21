"""受治理的知识来源与可重建检索分块。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from app.database import Base


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    knowledge_type = Column(String(40), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    source_uri = Column(String(1000), nullable=True)
    content_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    version = Column(Integer, nullable=False, default=1)
    metadata_json = Column(JSON, nullable=False, default=dict)
    valid_from = Column(DateTime, nullable=True, index=True)
    valid_to = Column(DateTime, nullable=True, index=True)
    index_status = Column(String(20), nullable=False, default="pending", index=True)
    supersedes_id = Column(Integer, ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "knowledge_type", "title", "version", name="uq_knowledge_source_version"),
        Index("ix_knowledge_scope_status", "user_id", "knowledge_type", "status"),
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_key = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    token_estimate = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source_id", "chunk_key", name="uq_knowledge_chunk_key"),
    )
