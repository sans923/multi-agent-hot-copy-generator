"""当前用户的长期偏好、反馈和可解释记忆条目。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user
from app.database import get_db
from app.models.memory import MemoryItem, UserPreference
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.memory import (
    FeedbackCreateRequest,
    FeedbackResponse,
    MemoryItemResponse,
    PreferencePatchRequest,
    PreferenceResponse,
    PublicationCreateRequest,
    PublicationMetricsPatch,
    PublicationResponse,
)
from app.services.feedback_learning_service import (
    build_memory_insights,
    record_publication,
    update_publication_metrics,
)
from app.services.memory_service import record_copy_feedback, upsert_user_preferences


router = APIRouter(prefix="/memory", tags=["长期记忆"])


@router.get("/insights", response_model=ApiResponse[dict])
def get_insights(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return ApiResponse(data=build_memory_insights(db, user_id=current_user.id))


@router.post(
    "/publications",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[PublicationResponse],
)
def create_publication(
    body: PublicationCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        row = record_publication(
            db,
            user_id=current_user.id,
            task_id=body.task_id,
            copy_id=body.copy_id,
            platform=body.platform,
            publication_status=body.status,
            external_id=body.external_id,
            url=body.url,
            metrics=body.metrics,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return ApiResponse(message="发布结果已记录", data=PublicationResponse.model_validate(row))


@router.patch(
    "/publications/{publication_id}/metrics",
    response_model=ApiResponse[PublicationResponse],
)
def patch_publication_metrics(
    publication_id: int,
    body: PublicationMetricsPatch,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        row = update_publication_metrics(
            db, user_id=current_user.id, publication_id=publication_id, metrics=body.metrics
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(message="发布指标已更新", data=PublicationResponse.model_validate(row))


@router.get("/preferences", response_model=ApiResponse[PreferenceResponse])
def get_preferences(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(UserPreference)
        .filter(UserPreference.user_id == current_user.id)
        .first()
    )
    data = PreferenceResponse(
        user_id=current_user.id,
        preferences=dict(row.preferences or {}) if row else {},
        version=int(row.version or 0) if row else 0,
        updated_at=row.updated_at if row else None,
    )
    return ApiResponse(data=data)


@router.put("/preferences", response_model=ApiResponse[PreferenceResponse])
def update_preferences(
    body: PreferencePatchRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        row = upsert_user_preferences(
            db,
            user_id=current_user.id,
            patch=body.preferences,
            expected_version=body.expected_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse(
        message="长期偏好已更新",
        data=PreferenceResponse(
            user_id=row.user_id,
            preferences=dict(row.preferences or {}),
            version=row.version,
            updated_at=row.updated_at,
        ),
    )


@router.post(
    "/feedback",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[FeedbackResponse],
)
def create_feedback(
    body: FeedbackCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        row = record_copy_feedback(
            db,
            user_id=current_user.id,
            task_id=body.task_id,
            copy_id=body.copy_id,
            action=body.action,
            rating=body.rating,
            comment=body.comment,
            metrics=body.metrics,
            idempotency_key=body.idempotency_key,
            edited_title=body.edited_title,
            edited_content=body.edited_content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ApiResponse(message="反馈已记录", data=FeedbackResponse.model_validate(row))


@router.get("/items", response_model=ApiResponse[list[MemoryItemResponse]])
def list_memory_items(
    memory_type: str = "",
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    query = db.query(MemoryItem).filter(
        MemoryItem.user_id == current_user.id,
        MemoryItem.status == "active",
        or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now),
    )
    if memory_type.strip():
        query = query.filter(MemoryItem.memory_type == memory_type.strip())
    rows = query.order_by(MemoryItem.updated_at.desc()).limit(limit).all()
    return ApiResponse(data=[MemoryItemResponse.model_validate(row) for row in rows])
