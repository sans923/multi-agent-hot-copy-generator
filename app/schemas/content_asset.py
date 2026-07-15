"""内容资产库 API Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ReferenceImportRequest(BaseModel):
    url: HttpUrl
    keyword: str = Field(min_length=1, max_length=100)
    like_count: int = Field(default=0, ge=0)
    read_count: int = Field(default=0, ge=0)
    comment_count: int = Field(default=0, ge=0)


class ReferenceResponse(BaseModel):
    id: int
    article_id: str
    title: str
    author_name: str | None = None
    keyword: str | None = None
    source_url: str | None = None
    like_count: int
    read_count: int
    comment_count: int
    embedding_status: str
    chunk_count: int
    content_length: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StyleCardBuildRequest(BaseModel):
    topic_cluster: str = Field(min_length=1, max_length=100)
    reference_ids: list[int] = Field(min_length=1, max_length=3)


class StyleCardResponse(BaseModel):
    id: int
    topic_cluster: str
    platform: str
    pattern_json: dict[str, Any]
    avg_like_count: int
    source_article_ids: list[str]
    confidence: float
    created_at: datetime | None = None
    updated_at: datetime | None = None
