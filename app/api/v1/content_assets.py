"""管理员内容资产库：头条参考文章与风格卡。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_admin_user
from app.database import get_db
from app.models.style_card import StyleCard
from app.models.toutiao_reference import ToutiaoReference
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationResponse
from app.schemas.content_asset import (
    ReferenceImportRequest,
    ReferenceResponse,
    StyleCardBuildRequest,
    StyleCardResponse,
)
from app.services.content_asset_service import (
    build_style_card,
    delete_reference,
    import_reference,
    reference_to_dict,
    reindex_reference,
    style_card_to_dict,
)


router = APIRouter(prefix="/content-assets", tags=["内容资产库"])


@router.get("/references", response_model=ApiResponse[PaginationResponse[ReferenceResponse]])
def list_references(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str = "",
    embedding_status: str = "",
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    query = db.query(ToutiaoReference)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(ToutiaoReference.title.like(like), ToutiaoReference.keyword.like(like)))
    if embedding_status.strip():
        query = query.filter(ToutiaoReference.embedding_status == embedding_status.strip())
    total = query.count()
    rows = query.order_by(ToutiaoReference.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ApiResponse(data=PaginationResponse(
        items=[ReferenceResponse(**reference_to_dict(row)) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    ))


@router.post("/references", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[ReferenceResponse])
def create_reference(
    body: ReferenceImportRequest,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        row = import_reference(
            db,
            url=str(body.url),
            keyword=body.keyword.strip(),
            like_count=body.like_count,
            read_count=body.read_count,
            comment_count=body.comment_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"文章抓取或向量化失败：{exc}") from exc
    return ApiResponse(message="参考文章已导入并完成向量化", data=ReferenceResponse(**reference_to_dict(row)))


@router.post("/references/{reference_id}/reindex", response_model=ApiResponse[ReferenceResponse])
def reindex_reference_route(
    reference_id: int,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    row = db.query(ToutiaoReference).filter_by(id=reference_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="参考文章不存在")
    try:
        row = reindex_reference(db, row)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"重新向量化失败：{exc}") from exc
    return ApiResponse(message="重新向量化完成", data=ReferenceResponse(**reference_to_dict(row)))


@router.delete("/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_reference(
    reference_id: int,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    row = db.query(ToutiaoReference).filter_by(id=reference_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="参考文章不存在")
    delete_reference(db, row)


@router.get("/style-cards", response_model=ApiResponse[list[StyleCardResponse]])
def list_style_cards(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(StyleCard)
        .filter(
            or_(StyleCard.owner_id.is_(None), StyleCard.owner_id == current_user.id),
            StyleCard.status != "deprecated",
        )
        .order_by(StyleCard.priority.asc(), StyleCard.updated_at.desc())
        .all()
    )
    return ApiResponse(data=[StyleCardResponse(**style_card_to_dict(row)) for row in rows])


@router.post("/style-cards", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[StyleCardResponse])
def create_style_card(
    body: StyleCardBuildRequest,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        card = build_style_card(db, topic_cluster=body.topic_cluster.strip(), reference_ids=body.reference_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ApiResponse(message="风格卡已生成", data=StyleCardResponse(**style_card_to_dict(card)))


@router.delete("/style-cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_style_card(
    card_id: int,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    card = db.query(StyleCard).filter_by(id=card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="风格卡不存在")
    db.delete(card)
    db.commit()
