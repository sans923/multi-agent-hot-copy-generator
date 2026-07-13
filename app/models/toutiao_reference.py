"""
头条参考长文表（toutiao_reference）
====================================

【在整体 RAG 流程中的位置】
    位于「LangGraph 之前」和「LangGraph 之后」之间：

        fetch → 【MySQL 本表存全文】 → LangGraph ingest → Chroma 存向量块

【为什么需要 MySQL + Chroma 双存？】
    - MySQL：存完整原文、embedding_status、chunk_count，可管理、可重跑 ingest
    - Chroma：存切块向量，供 query 图 similarity_search

【与 hotlist_sync 的区别】
    hotlist_sync：只有热点标题（聚合 API）
    toutiao_reference：完整长文正文（抓取 + RAG）
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, Index, BigInteger

from app.database import Base


class ToutiaoReference(Base):
    """
    ORM 模型：一条记录 = 一篇头条长文。

    关键字段与流程：
        embedding_status=pending  → 已入库 MySQL，尚未跑完 LangGraph ingest
        embedding_status=completed → ingest 图跑完，chunk_count 已写入
    """

    __tablename__ = "toutiao_reference"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(String(64), unique=True, nullable=False, comment="头条文章ID")
    title = Column(String(500), nullable=False, comment="标题")
    content = Column(Text, nullable=False, comment="正文全文")
    author_name = Column(String(100), nullable=True, comment="作者")
    keyword = Column(String(100), nullable=True, comment="采集关键词")
    source_url = Column(Text, nullable=True, comment="原文链接")

    like_count = Column(BigInteger, default=0, nullable=False, comment="点赞数")
    read_count = Column(BigInteger, default=0, nullable=False, comment="阅读数")
    comment_count = Column(BigInteger, default=0, nullable=False, comment="评论数")
    publish_time = Column(DateTime, nullable=True, comment="发布时间")

    embedding_status = Column(String(20), default="pending", nullable=False)
    chunk_count = Column(Integer, default=0, comment="LangGraph ingest 写入向量库的块数")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_toutiao_ref_status", "embedding_status"),
        Index("idx_toutiao_ref_keyword", "keyword"),
        Index("idx_toutiao_ref_like_count", "like_count"),
    )
