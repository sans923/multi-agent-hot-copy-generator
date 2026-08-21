"""长期记忆 API 输入输出 Schema。"""

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class PreferencePatchRequest(BaseModel):
    preferences: dict[str, Any] = Field(min_length=1, max_length=30)
    expected_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_size(self):
        if len(json.dumps(self.preferences, ensure_ascii=False)) > 10_000:
            raise ValueError("偏好数据不能超过 10000 个 JSON 字符")
        if any(str(key).startswith("_") for key in self.preferences):
            raise ValueError("偏好键不能使用保留前缀 _")
        return self


class PreferenceResponse(BaseModel):
    user_id: int
    preferences: dict[str, Any]
    version: int
    updated_at: datetime | None = None


class FeedbackCreateRequest(BaseModel):
    task_id: int = Field(ge=1)
    copy_id: int = Field(ge=1)
    action: Literal["accepted", "rejected", "edited", "published"]
    rating: int = Field(ge=-1, le=1)
    comment: str = Field(default="", max_length=1000)
    metrics: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=100)
    edited_title: str | None = Field(default=None, max_length=200)
    edited_content: str | None = Field(default=None, min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def validate_metrics_size(self):
        if len(json.dumps(self.metrics, ensure_ascii=False)) > 10_000:
            raise ValueError("指标数据不能超过 10000 个 JSON 字符")
        if self.action == "edited" and not (self.edited_content or "").strip():
            raise ValueError("edited 反馈必须提供 edited_content")
        if self.action != "edited" and (
            self.edited_title is not None or self.edited_content is not None
        ):
            raise ValueError("只有 edited 反馈可以提交编辑后的标题或正文")
        return self


class FeedbackResponse(BaseModel):
    id: int
    task_id: int
    copy_id: int
    action: str
    rating: int
    comment: str | None = None
    metrics: dict[str, Any]
    idempotency_key: str
    created_at: datetime
    result_copy_id: int | None = None

    class Config:
        from_attributes = True


class MemoryItemResponse(BaseModel):
    id: int
    memory_type: str
    scope_id: str
    source_type: str
    source_id: str
    content: str
    status: str
    schema_version: int
    version: int
    confidence: float
    quality_score: float
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
