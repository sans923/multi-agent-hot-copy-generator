"""终稿发布准备：头条辅助发布、抖音 H5 用户确认投稿。"""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_active_user
from app.database import get_db
from app.models.copy import Copy
from app.models.task import Task
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.publishing import (
    PublishPreparationRequest,
    PublishPreparationResponse,
)
from app.services.audit_service import write_audit_log
from app.services.publishing_service import (
    DouyinOpenPlatformClient,
    DouyinOpenPlatformError,
    prepare_douyin_publication,
    prepare_toutiao_publication,
    is_allowed_media_host,
)


router = APIRouter(prefix="/tasks", tags=["内容发布准备"])


@lru_cache(maxsize=1)
def _get_douyin_client() -> DouyinOpenPlatformClient:
    return DouyinOpenPlatformClient(
        client_key=settings.DOUYIN_CLIENT_KEY,
        client_secret=settings.DOUYIN_CLIENT_SECRET,
        base_url=settings.DOUYIN_API_BASE_URL,
        timeout=settings.DOUYIN_HTTP_TIMEOUT_SECONDS,
    )


@router.post(
    "/{task_id}/publish-preparation",
    response_model=ApiResponse[PublishPreparationResponse],
    summary="准备头条发布包或抖音用户确认投稿",
)
def prepare_publication(
    task_id: int,
    body: PublishPreparationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ApiResponse[PublishPreparationResponse]:
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.user_id == current_user.id,
    ).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    final_copy = (
        db.query(Copy)
        .filter(
            Copy.id == body.copy_id,
            Copy.task_id == task.id,
            Copy.is_final.is_(True),
        )
        .first()
    )
    if final_copy is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="所选文案不是该任务的有效终稿，不能准备发布",
        )

    if body.platform == "toutiao":
        preparation = prepare_toutiao_publication(final_copy)
    else:
        ticket = None
        external_blocker = None
        if settings.DOUYIN_H5_SHARE_ENABLED and not settings.DOUYIN_CLIENT_SECRET.strip():
            external_blocker = "未配置 DOUYIN_CLIENT_SECRET"
        can_request_ticket = all(
            (
                settings.DOUYIN_H5_SHARE_ENABLED,
                settings.DOUYIN_CLIENT_KEY.strip(),
                settings.DOUYIN_CLIENT_SECRET.strip(),
                body.media_url is not None,
                is_allowed_media_host(
                    body.media_url,
                    settings.DOUYIN_MEDIA_ALLOWED_HOSTS,
                ),
            )
        )
        if can_request_ticket:
            try:
                ticket = _get_douyin_client().get_open_ticket()
            except DouyinOpenPlatformError as exc:
                external_blocker = str(exc)
        preparation = prepare_douyin_publication(
            final_copy,
            body,
            enabled=settings.DOUYIN_H5_SHARE_ENABLED,
            client_key=settings.DOUYIN_CLIENT_KEY,
            ticket=ticket,
            allowed_media_hosts=settings.DOUYIN_MEDIA_ALLOWED_HOSTS,
            external_blocker=external_blocker,
        )

    write_audit_log(
        db,
        task.id,
        "human",
        "publish_preparation",
        input_summary={
            "platform": body.platform,
            "copy_id": body.copy_id,
            "media_type": body.media_type,
        },
        output_summary={
            "mode": preparation.mode,
            "ready": preparation.ready,
            "requires_user_confirmation": preparation.requires_user_confirmation,
            "blocker_count": len(preparation.blockers),
        },
        status="success" if preparation.ready else "blocked",
    )

    from datetime import datetime

    task.publication_status = "ready" if preparation.ready else "not_prepared"
    task.status_reason = None if preparation.ready else "; ".join(preparation.blockers)[:500]
    task.status_updated_at = datetime.utcnow()
    db.commit()

    return ApiResponse(
        success=True,
        message="发布准备已完成" if preparation.ready else "发布准备存在阻断项",
        data=preparation,
    )
