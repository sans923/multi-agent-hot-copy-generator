"""
风格卡（Style Card）模型
========================
离线从爆款长文提取的「抽象写作规律」沉淀，在线创作时按话题选用。
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, Float, JSON, Index

from app.database import Base


class StyleCard(Base):
    __tablename__ = "style_cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_cluster = Column(String(100), nullable=False, index=True, comment="话题簇/关键词")
    platform = Column(String(30), default="toutiao", nullable=False, comment="适用平台")
    pattern_json = Column(JSON, nullable=False, comment="抽象写作规律 JSON")
    avg_like_count = Column(Integer, default=0, comment="来源文章平均点赞")
    source_article_ids = Column(JSON, nullable=True, comment="来源 article_id 列表")
    confidence = Column(Float, default=0.0, comment="规律提取置信度")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_style_card_topic_platform", "topic_cluster", "platform"),
    )
