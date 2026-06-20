"""
热榜数据查询接口（/api/v1/hotlist）
=====================================
提供：
- GET  /                 查询最新热榜列表（支持平台过滤、分页）
- GET  /platforms        获取支持的平台列表
- GET  /search           语义搜索热榜（输入一段话，找最相关的热榜话题）
- POST /sync             手动触发同步（管理员）
- POST /sync/{platform}  手动触发单平台同步（管理员）
- GET  /stats            热榜统计信息（管理员）
"""

import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.hotlist_sync import HotlistSync
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationResponse
from app.core.deps import get_current_active_user, get_current_admin_user
from app.services.hotlist_service import (
    sync_all_hotlists,
    sync_single_platform,
    get_recent_hotlist,
    JUHE_PLATFORM_KEY,
)
from app.utils.logger import logger


router = APIRouter(prefix="/hotlist", tags=["热榜数据"])


# ====================================================
# 热榜数据 Schema（响应格式）
# ====================================================

from datetime import datetime
from pydantic import BaseModel


class HotlistItemResponse(BaseModel):
    """单条热榜话题的响应格式"""
    id: int
    source_platform: str
    rank: Optional[int] = None
    title: str
    description: Optional[str] = None
    hot_value: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    embedding_status: str
    fetched_at: datetime

    class Config:
        from_attributes = True


class HotlistSearchResult(BaseModel):
    """语义搜索结果"""
    title: str
    platform: str
    rank: int
    hot_value: str
    similarity: float     # 相似度 0~1（越大越相关）
    distance: float       # 向量距离（越小越相关）


# ====================================================
# 接口实现
# ====================================================

@router.get(
    "/platforms",
    response_model=ApiResponse[list[dict]],
    summary="获取支持的热榜平台"
)
def get_platforms():
    """返回所有支持的热榜平台配置信息"""
    platforms = [
        {
            "key": JUHE_PLATFORM_KEY,
            "display_name": "综合热搜（聚合数据）",
            "max_items": 50,
        }
    ]
    return ApiResponse(success=True, message="获取成功", data=platforms)


@router.get(
    "/",
    response_model=ApiResponse[PaginationResponse[HotlistItemResponse]],
    summary="查询热榜列表",
    description="获取最新热榜数据，支持按平台过滤和分页"
)
def list_hotlist(
    platform: Optional[str] = Query(
        default=None,
        description=f"平台过滤：当前仅支持 {JUHE_PLATFORM_KEY}"
    ),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    查询最新有效热榜数据（未过期的）
    
    业务场景：
    - 用户在创建文案任务前，可以浏览当前热榜，选择感兴趣的话题
    - 也可以不选择，让 Agent 自动匹配相关热点
    """
    # 验证平台参数
    if platform and platform != JUHE_PLATFORM_KEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的平台: {platform}，当前支持: [{JUHE_PLATFORM_KEY}]"
        )

    query = db.query(HotlistSync).filter(HotlistSync.is_expired == 0)

    if platform:
        query = query.filter(HotlistSync.source_platform == platform)

    total = query.count()
    items = (
        query
        .order_by(HotlistSync.fetched_at.desc(), HotlistSync.rank.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ApiResponse(
        success=True,
        message="获取成功",
        data=PaginationResponse(
            items=[HotlistItemResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )
    )


@router.get(
    "/search",
    response_model=ApiResponse[list[HotlistSearchResult]],
    summary="语义搜索热榜",
    description="输入一段描述，用 AI 语义匹配找出最相关的热榜话题"
)
def search_hotlist_semantic(
    query: str = Query(description="搜索描述，如'美妆护肤相关话题'"),
    platform: Optional[str] = Query(default=None, description="限定平台（可选）"),
    n_results: int = Query(default=5, ge=1, le=20, description="返回条数"),
    current_user: User = Depends(get_current_active_user),
):
    """
    语义搜索是这个系统的核心竞争力之一：
    
    传统关键词搜索：搜"环保" -> 只找到标题含"环保"的
    语义搜索：搜"环保" -> 还能找到"新能源汽车""碳中和""垃圾分类"等相关话题
    
    这里调用 ChromaDB 的向量相似度搜索
    """
    if not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="搜索内容不能为空"
        )

    from app.services.embedding_service import search_hotlist

    try:
        results = search_hotlist(
            query=query,
            n_results=n_results,
            platform_filter=platform,
        )
    except Exception as e:
        logger.error(f"语义搜索失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"语义搜索服务暂不可用: {str(e)}"
        )

    return ApiResponse(
        success=True,
        message=f"找到 {len(results)} 条相关热榜",
        data=[HotlistSearchResult(**r) for r in results]
    )


@router.post(
    "/sync",
    response_model=ApiResponse[dict],
    summary="手动触发全量热榜同步（管理员）",
    description="立即抓取所有平台热榜，不等定时任务"
)
async def trigger_full_sync(
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(get_current_admin_user),
):
    """
    管理员手动触发同步
    
    使用 BackgroundTasks 在后台异步执行同步任务（不阻塞API响应）
    立即返回"已触发"，同步在后台进行
    
    BackgroundTasks：FastAPI 内置的轻量级后台任务
    - 请求处理完成后执行
    - 不是真正的异步（还是同一进程）
    - 适合轻量级后台操作，重量级用 Celery
    """
    background_tasks.add_task(_run_sync_all)

    logger.info(f"管理员 {current_admin.username} 触发全量热榜同步")
    return ApiResponse(
        success=True,
        message="同步任务已在后台启动，请稍后查看结果",
        data={"triggered_by": current_admin.username}
    )


async def _run_sync_all():
    """在后台运行同步任务的包装函数"""
    try:
        stats = await sync_all_hotlists()
        logger.info(f"手动触发同步完成: {stats}")
    except Exception as e:
        logger.error(f"手动触发同步失败: {e}")


@router.post(
    "/sync/{platform}",
    response_model=ApiResponse[dict],
    summary="手动触发单平台同步（管理员）"
)
async def trigger_platform_sync(
    platform: str,
    current_admin: User = Depends(get_current_admin_user),
):
    """同步热榜（测试或补偿用，platform 参数保留以兼容旧接口）"""
    try:
        count = await sync_single_platform(platform)
        return ApiResponse(
            success=True,
            message=f"聚合数据热榜同步完成",
            data={"platform": JUHE_PLATFORM_KEY, "synced_count": count}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"同步失败: {str(e)}"
        )


@router.get(
    "/stats",
    response_model=ApiResponse[dict],
    summary="热榜统计信息（管理员）"
)
def get_hotlist_stats(
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    统计各平台热榜数据情况
    用于运维监控：数据是否及时更新？向量化是否有积压？
    """
    # 各平台有效数据条数
    platform_counts = (
        db.query(HotlistSync.source_platform, func.count(HotlistSync.id))
        .filter(HotlistSync.is_expired == 0)
        .group_by(HotlistSync.source_platform)
        .all()
    )

    # 待向量化数量
    pending_embedding = (
        db.query(func.count(HotlistSync.id))
        .filter(HotlistSync.embedding_status == "pending", HotlistSync.is_expired == 0)
        .scalar()
    )

    # 最近一次同步时间
    latest_sync = (
        db.query(func.max(HotlistSync.fetched_at))
        .scalar()
    )

    # 总历史记录数
    total_records = db.query(func.count(HotlistSync.id)).scalar()

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "active_by_platform": {p: c for p, c in platform_counts},
            "pending_embedding": pending_embedding,
            "latest_sync_time": latest_sync.isoformat() if latest_sync else None,
            "total_historical_records": total_records,
        }
    )
