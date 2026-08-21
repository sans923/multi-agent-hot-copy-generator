"""当前用户的版本化知识来源与可引用检索。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user
from app.database import get_db
from app.models.knowledge import KnowledgeSource
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.knowledge import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSourceCreate,
    KnowledgeSourceResponse,
)
from app.services.knowledge_service import create_knowledge_source, search_knowledge


router = APIRouter(prefix="/knowledge", tags=["知识库"])


def _source_response(row: KnowledgeSource) -> KnowledgeSourceResponse:
    return KnowledgeSourceResponse(
        id=row.id,
        user_id=row.user_id,
        knowledge_type=row.knowledge_type,
        title=row.title,
        source_uri=row.source_uri,
        status=row.status,
        version=row.version,
        metadata=dict(row.metadata_json or {}),
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        index_status=row.index_status,
        created_at=row.created_at,
    )


@router.post(
    "/sources",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[KnowledgeSourceResponse],
)
def create_source(
    body: KnowledgeSourceCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        row = create_knowledge_source(
            db,
            user_id=current_user.id,
            knowledge_type=body.knowledge_type,
            title=body.title,
            content=body.content,
            source_uri=body.source_uri,
            metadata=body.metadata,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ApiResponse(message="知识来源已入库", data=_source_response(row))


@router.get("/sources", response_model=ApiResponse[list[KnowledgeSourceResponse]])
def list_sources(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.user_id == current_user.id)
        .order_by(KnowledgeSource.updated_at.desc())
        .all()
    )
    return ApiResponse(data=[_source_response(row) for row in rows])


@router.post("/search", response_model=ApiResponse[KnowledgeSearchResponse])
def search_sources(
    body: KnowledgeSearchRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    result = search_knowledge(
        db,
        user_id=current_user.id,
        query=body.query,
        knowledge_types=list(body.knowledge_types),
        limit=body.limit,
    )
    return ApiResponse(data=KnowledgeSearchResponse(**result))
