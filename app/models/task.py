"""
任务表模型（tasks）
==================
每次用户发起"生成文案"的请求，就创建一条 Task 记录
Task 是整个系统的工作单元，3个 Agent 都围绕它协作

生命周期：
  pending（等待）-> processing（Agent处理中）-> completed（完成）/ failed（失败）
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class TaskStatus(str, enum.Enum):
    """
    任务状态枚举
    
    用枚举而不是裸字符串的好处：
    1. 防止拼写错误（task.status = "pendng" 这种错误会被捕获）
    2. 代码提示更好（IDE自动补全）
    3. 数据库层面约束（只能存这几个值）
    
    继承 str 让它可以直接和字符串比较：
    task.status == "pending" -> True
    """
    PENDING = "pending"        # 已创建，等待Agent处理
    PROCESSING = "processing"  # Agent正在处理中
    AWAITING_HUMAN = "awaiting_human"  # 需人工介入（Agentic 编排暂停）
    COMPLETED = "completed"    # 处理完成，有结果
    FAILED = "failed"          # 处理失败


class TaskPlatform(str, enum.Enum):
    """目标发布平台"""
    TOUTIAO = "toutiao"        # 今日头条长文
    WEIBO = "weibo"            # 微博
    WECHAT = "wechat"          # 微信公众号
    DOUYIN = "douyin"          # 抖音/短视频脚本
    XIAOHONGSHU = "xiaohongshu" # 小红书
    ZHIHU = "zhihu"            # 知乎


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="任务ID")

    # ForeignKey 建立外键关联：tasks.user_id -> users.id
    # 这确保 task 必须属于一个存在的 user
    # ondelete="CASCADE"：删除用户时，关联的任务也自动删除
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="发起任务的用户ID"
    )

    # 用户的原始需求描述（需求理解Agent的输入）
    raw_requirement = Column(
        Text,
        nullable=False,
        comment="用户原始需求描述"
    )

    # 目标平台
    platform = Column(
        Enum(TaskPlatform),
        nullable=False,
        default=TaskPlatform.WEIBO,
        comment="目标发布平台"
    )

    # 任务状态，使用 Enum 类型
    status = Column(
        Enum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
        comment="任务状态"
    )

    # JSON 字段：存储需求理解Agent解析出的结构化需求
    # 例如：{"topic": "AI技术", "style": "幽默", "keywords": ["创新", "颠覆"]}
    # JSON 字段灵活，不需要固定结构，适合存储半结构化数据
    parsed_requirement = Column(
        JSON,
        nullable=True,
        comment="需求理解Agent解析后的结构化需求"
    )

    # 关联的热榜话题ID（可为空，用户也可以不基于热榜生成）
    hotlist_id = Column(
        Integer,
        ForeignKey("hotlist_sync.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的热榜话题ID"
    )

    # 错误信息（失败时记录原因）
    error_message = Column(Text, nullable=True, comment="失败原因")

    # Agentic 编排元数据（task_mode / plan / checkpoint / verification 等）
    orchestration_meta = Column(
        JSON,
        nullable=True,
        comment="编排元数据：task_mode、plan_source、checkpoint 等",
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间")

    # ORM 关联关系
    user = relationship("User", back_populates="tasks")
    copies = relationship("Copy", back_populates="task", lazy="dynamic")
    agent_logs = relationship("AgentLog", back_populates="task", lazy="dynamic")
    audit_logs = relationship("OrchestrationAuditLog", back_populates="task", lazy="dynamic")
    hotlist = relationship("HotlistSync", back_populates="tasks")

    def __repr__(self) -> str:
        return f"<Task id={self.id} status={self.status} user_id={self.user_id}>"
