"""
任务接口（/api/v1/tasks）
==========================
提供：
- POST /           创建文案生成任务（触发 3 Agent 流程）
- GET  /           获取当前用户的任务列表
- GET  /{task_id}  获取任务详情（含生成的文案）
- GET  /{task_id}/copies  获取任务下所有文案版本

【任务执行方式】
为了不让 HTTP 请求超时（3个Agent调用可能需要30-60秒），
任务采用后台线程执行：
  POST /tasks -> 立即返回 task_id（状态=pending）
  后台线程异步执行 AgentOrchestrator.run()
  前端轮询 GET /tasks/{task_id} 查看状态
"""

import threading
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models.task import Task, TaskStatus, TaskPlatform
from app.models.copy import Copy
from app.models.user import User
from app.schemas.task import (
    TaskCreate,
    TaskResponse,
    TaskDetailResponse,
    TaskCopySummary,
    CopyResponse,
)
from app.schemas.common import ApiResponse, PaginationResponse
from app.core.deps import get_current_active_user
from app.utils.logger import logger


router = APIRouter(prefix="/tasks", tags=["文案生成任务"])


def _run_agents_background(task_id: int) -> None:
    """
    后台执行 Agent 编排流程
    
    为什么要在独立函数里创建新的 db session？
    因为 FastAPI 的请求级 Session 在请求结束后就关闭了，
    后台线程必须自己创建独立的 Session
    """
    db = SessionLocal()
    try:
        # 双引擎切换的唯一接缝：按配置 settings.ORCHESTRATION_ENGINE 取编排引擎并调用。
        # 默认 "native"（自研 AgentOrchestrator），切换为 "langgraph" 即用 LangGraph 引擎；
        # 统一接口 run(db, task_id) -> dict 与历史保持一致，API/前端/事务管理均无需改动。
        from app.config import settings
        from app.orchestration import get_orchestration_engine
        engine = get_orchestration_engine(settings.ORCHESTRATION_ENGINE)
        result = engine.run(db=db, task_id=task_id)
        logger.info(f"后台任务执行完成: task_id={task_id}, success={result.get('success')}")
    except Exception as e:
        logger.exception(f"后台任务执行异常: task_id={task_id}")
        # 更新任务状态为失败
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)[:500]
            db.commit()
    finally:
        db.close()


@router.post(
    "/",
    response_model=ApiResponse[TaskResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建文案生成任务",
    description="提交需求，后台异步执行3个Agent生成文案，立即返回task_id"
)
def create_task(
    task_data: TaskCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TaskResponse]:
    """
    创建任务流程：
    1. 创建 Task 记录（status=pending）
    2. 立即返回 task_id 给客户端
    3. 后台异步启动 3 个 Agent 流程
    
    客户端拿到 task_id 后，每隔 3-5 秒轮询 GET /tasks/{task_id}
    直到 status 变为 completed 或 failed
    """
    # 创建任务记录
    task = Task(
        user_id=current_user.id,
        raw_requirement=task_data.raw_requirement,
        platform=task_data.platform,
        hotlist_id=task_data.hotlist_id,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    logger.info(
        f"新任务创建: task_id={task.id}, user_id={current_user.id}, "
        f"platform={task_data.platform}"
    )

    # 后台异步执行 Agent（不阻塞 HTTP 响应）
    # BackgroundTasks 是 FastAPI 内置的后台任务，请求返回后自动执行
    # 注意：对于耗时很长的任务，推荐用 Celery，这里用线程够用了
    background_tasks.add_task(_run_agents_background, task.id)

    return ApiResponse(
        success=True,
        message="任务已创建，正在后台生成文案，请轮询任务状态",
        data=TaskResponse.model_validate(task)
    )


@router.get(
    "/",
    response_model=ApiResponse[PaginationResponse[TaskResponse]],
    summary="获取任务列表",
)
def list_tasks(
    page: int = 1,
    page_size: int = 20,
    status_filter: str = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ApiResponse[PaginationResponse[TaskResponse]]:
    """获取当前用户的所有任务"""
    query = db.query(Task).filter(Task.user_id == current_user.id)

    if status_filter:
        try:
            query = query.filter(Task.status == TaskStatus(status_filter))
        except ValueError:
            pass

    total = query.count()
    tasks = (
        query
        .order_by(Task.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ApiResponse(
        success=True,
        message="获取成功",
        data=PaginationResponse(
            items=[TaskResponse.model_validate(t) for t in tasks],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )
    )


@router.get(
    "/{task_id}",
    response_model=ApiResponse[TaskDetailResponse],
    summary="获取任务详情",
    description="包含任务状态和生成的文案列表，通过轮询此接口获取生成结果"
)
def get_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TaskDetailResponse]:
    """
    获取任务详情
    
    前端轮询逻辑示例：
        status = "pending"
        while status not in ["completed", "failed"]:
            time.sleep(3)
            response = GET /tasks/{task_id}
            status = response.data.status
        show_result(response.data.copies)
    """
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.user_id == current_user.id  # 只能查自己的任务
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务 {task_id} 不存在"
        )

    # 获取该任务的所有文案
    copies = (
        db.query(Copy)
        .filter(Copy.task_id == task_id)
        .order_by(Copy.version)
        .all()
    )

    # 不能 TaskDetailResponse.model_validate(task)：Task.copies 关系是 ORM 对象，会触发校验失败
    task_base = TaskResponse.model_validate(task)
    task_detail = TaskDetailResponse(
        **task_base.model_dump(),
        copies=[TaskCopySummary.model_validate(c) for c in copies],
    )

    return ApiResponse(
        success=True,
        message=f"任务状态：{task.status.value}",
        data=task_detail
    )


@router.get(
    "/{task_id}/copies",
    response_model=ApiResponse[list[CopyResponse]],
    summary="获取任务下所有文案版本",
)
def get_task_copies(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[CopyResponse]]:
    """获取任务下所有版本的文案（初稿+终稿）"""
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.user_id == current_user.id
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务 {task_id} 不存在"
        )

    copies = (
        db.query(Copy)
        .filter(Copy.task_id == task_id)
        .order_by(Copy.version)
        .all()
    )

    return ApiResponse(
        success=True,
        message=f"共 {len(copies)} 个版本",
        data=[CopyResponse.model_validate(c) for c in copies]
    )
