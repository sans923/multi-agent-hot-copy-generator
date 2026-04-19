"""
用户管理接口（/api/v1/users）
==============================
提供：
- GET  /me         获取自己的用户信息
- PUT  /me         更新自己的用户信息
- GET  /           管理员：获取所有用户列表
- GET  /{user_id}  管理员：获取指定用户信息
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from app.schemas.common import ApiResponse, PaginationResponse, PaginationParams
from app.core.security import hash_password
from app.core.deps import get_current_active_user, get_current_admin_user
from app.utils.logger import logger


router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get(
    "/me",
    response_model=ApiResponse[UserResponse],
    summary="获取当前用户详情"
)
def get_my_profile(
    current_user: User = Depends(get_current_active_user)
) -> ApiResponse[UserResponse]:
    return ApiResponse(
        success=True,
        message="获取成功",
        data=UserResponse.model_validate(current_user)
    )


@router.put(
    "/me",
    response_model=ApiResponse[UserResponse],
    summary="更新当前用户信息"
)
def update_my_profile(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ApiResponse[UserResponse]:
    """
    只更新传了值的字段（PATCH 语义）
    使用 model_dump(exclude_unset=True) 过滤掉未传的字段
    """
    update_fields = update_data.model_dump(exclude_unset=True)

    # 如果要更新密码，需要先哈希
    if "password" in update_fields:
        update_fields["hashed_password"] = hash_password(update_fields.pop("password"))

    # 逐字段更新
    for field, value in update_fields.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)

    logger.info(f"用户更新信息: id={current_user.id} fields={list(update_fields.keys())}")

    return ApiResponse(
        success=True,
        message="更新成功",
        data=UserResponse.model_validate(current_user)
    )


@router.get(
    "/",
    response_model=ApiResponse[PaginationResponse[UserResponse]],
    summary="获取用户列表（管理员）",
    description="需要管理员权限"
)
def list_users(
    page: int = 1,
    page_size: int = 20,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> ApiResponse[PaginationResponse[UserResponse]]:
    """管理员查看所有用户"""
    total = db.query(User).count()
    users = db.query(User).offset((page - 1) * page_size).limit(page_size).all()

    return ApiResponse(
        success=True,
        message="获取成功",
        data=PaginationResponse(
            items=[UserResponse.model_validate(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size
        )
    )


@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserResponse],
    summary="获取指定用户信息（管理员）"
)
def get_user_by_id(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> ApiResponse[UserResponse]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 ID={user_id} 不存在"
        )
    return ApiResponse(
        success=True,
        message="获取成功",
        data=UserResponse.model_validate(user)
    )
