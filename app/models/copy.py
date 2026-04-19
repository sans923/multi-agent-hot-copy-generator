"""
文案表模型（copies）
===================
存储 Agent 生成的每一份文案内容
一个 Task 可以有多份文案（比如迭代优化后的不同版本）

版本控制设计：
- version=1: 文案创作Agent生成的初稿
- version=2: 审核优化Agent改进后的终稿
- 最多2个版本（方案中规定审稿Agent最多迭代1次）
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON, Boolean
from sqlalchemy.orm import relationship

from app.database import Base


class Copy(Base):
    __tablename__ = "copies"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="文案ID")

    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属任务ID"
    )

    # 版本号：1=初稿，2=优化稿
    version = Column(
        Integer,
        nullable=False,
        default=1,
        comment="版本号（1=初稿，2=审核优化后）"
    )

    # 文案标题
    title = Column(String(200), nullable=True, comment="文案标题")

    # 文案正文（核心内容）
    content = Column(Text, nullable=False, comment="文案正文内容")

    # 话题标签（如 #AI技术 #创业 ）
    hashtags = Column(JSON, nullable=True, comment="话题标签列表")

    # 目标平台（冗余存储，方便直接查询，不用 JOIN tasks 表）
    platform = Column(String(30), nullable=True, comment="目标发布平台")

    # 审核分数（0-100）：审核Agent给出的质量评分
    review_score = Column(
        Float,
        nullable=True,
        comment="审核Agent评分(0-100)"
    )

    # 审核意见（审核Agent的详细评价）
    review_comment = Column(Text, nullable=True, comment="审核Agent评审意见")

    # 是否是最终被采用的版本
    is_final = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否是最终版本"
    )

    # 用于生成此文案时使用的热榜关键词
    hot_keywords = Column(JSON, nullable=True, comment="关联的热榜关键词")

    # 写作风格（幽默/严肃/煽情/专业 等）
    tone = Column(String(50), nullable=True, comment="文案风格/语气")

    # Token 消耗量（用于统计 API 成本）
    tokens_used = Column(Integer, default=0, comment="生成此文案消耗的token数")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="生成时间")

    task = relationship("Task", back_populates="copies")

    def __repr__(self) -> str:
        return f"<Copy id={self.id} task_id={self.task_id} version={self.version} score={self.review_score}>"
