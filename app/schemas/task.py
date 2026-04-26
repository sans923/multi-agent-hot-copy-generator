"""
任务相关 Pydantic Schema
"""

from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field
from app.models.task import TaskStatus, TaskPlatform


class TaskCreate(BaseModel):
    """创建任务的请求体"""
    raw_requirement: str = Field(
        min_length=5,
        max_length=1000,
        description="文案需求描述，尽量详细",
        examples=["帮我写一篇关于最新AI技术突破的微博，风格幽默，要蹭热点"]
    )
    platform: TaskPlatform = Field(
        default=TaskPlatform.WEIBO,
        description="目标发布平台"
    )
    hotlist_id: Optional[int] = Field(
        default=None,
        description="指定关联的热榜话题ID（可选）"
    )


class TaskResponse(BaseModel):
    """任务信息响应"""
    id: int
    user_id: int
    raw_requirement: str
    platform: str
    status: str
    parsed_requirement: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskDetailResponse(TaskResponse):
    """任务详情（含生成的文案列表）"""
    copies: list[dict] = []


class CopyResponse(BaseModel):
    """文案响应"""
    id: int
    task_id: int
    version: int
    title: Optional[str] = None
    content: str
    hashtags: Optional[list] = None
    platform: Optional[str] = None
    review_score: Optional[float] = None
    review_comment: Optional[str] = None
    is_final: bool
    tone: Optional[str] = None
    tokens_used: int
    created_at: datetime

    class Config:
        from_attributes = True
