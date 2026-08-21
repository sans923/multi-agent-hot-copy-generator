"""知识治理 API 契约。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


KnowledgeType = Literal[
    "brand_fact", "product_fact", "campaign_material", "platform_rule", "external_reference"
]


class KnowledgeSourceCreate(BaseModel):
    knowledge_type: KnowledgeType
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=200_000)
    source_uri: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class KnowledgeSourceResponse(BaseModel):
    id: int
    user_id: int | None
    knowledge_type: str
    title: str
    source_uri: str | None
    status: str
    version: int
    metadata: dict[str, Any]
    valid_from: datetime | None
    valid_to: datetime | None
    index_status: str
    created_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    knowledge_types: list[KnowledgeType] = Field(default_factory=list, max_length=5)
    limit: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchResponse(BaseModel):
    items: list[dict[str, Any]]
    citations: list[dict[str, Any]]
