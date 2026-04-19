"""
热榜同步记录表（hotlist_sync）
================================
存储从韩小韩 API 抓取的热榜数据
每1小时 APScheduler 自动更新一次

数据来源：https://api.vvhan.com/api/hotlist
支持平台：微博热搜 / 微信热点 / 抖音热搜 / B站热门 / 知乎热榜 等

这些热榜话题会被向量化存入 ChromaDB，
文案创作 Agent 可以搜索相关热点，让文案蹭热度
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Float
from sqlalchemy.orm import relationship

from app.database import Base


class HotlistSync(Base):
    __tablename__ = "hotlist_sync"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="记录ID")

    # 热榜来源平台（weibo / douyin / wechat / bilibili / zhihu）
    source_platform = Column(
        String(30),
        nullable=False,
        index=True,
        comment="热榜来源平台"
    )

    # 话题在热榜上的排名
    rank = Column(Integer, nullable=True, comment="热榜排名")

    # 热点话题标题（核心字段）
    title = Column(String(300), nullable=False, comment="热点话题标题")

    # 话题描述/摘要（有些平台有，有些没有）
    description = Column(Text, nullable=True, comment="话题描述")

    # 热度值/热搜指数
    hot_value = Column(String(50), nullable=True, comment="热度值（如 1234万）")

    # 话题原始 URL（跳转到话题详情页）
    url = Column(Text, nullable=True, comment="话题原始链接")

    # 话题图片 URL（封面图）
    image_url = Column(Text, nullable=True, comment="话题图片链接")

    # 额外数据（原始 API 响应，方便后期扩展）
    extra_data = Column(JSON, nullable=True, comment="API原始响应数据")

    # 向量化状态：pending/completed
    embedding_status = Column(
        String(20),
        default="pending",
        nullable=False,
        comment="向量化状态"
    )

    # 在 ChromaDB 中的 ID（用于精确删除和更新）
    chroma_id = Column(String(100), nullable=True, comment="ChromaDB中的文档ID")

    # 话题热度评分（由系统计算，综合排名和热度值，用于推荐）
    relevance_score = Column(Float, nullable=True, comment="系统计算的热度评分")

    # 该条数据抓取时间
    fetched_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="数据抓取时间"
    )

    # 该条数据是否已过期（超过24小时认为过期）
    is_expired = Column(
        Integer,
        default=0,
        nullable=False,
        comment="是否过期（0=有效，1=过期）"
    )

    tasks = relationship("Task", back_populates="hotlist")

    def __repr__(self) -> str:
        return f"<HotlistSync id={self.id} platform={self.source_platform} rank={self.rank} title={self.title[:30]}>"
