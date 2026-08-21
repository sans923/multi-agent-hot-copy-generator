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
from app.models.style_card import StyleCard
from app.schemas.task import (
    TaskCreate,
    TaskResponse,
    TaskDetailResponse,
    TaskCopySummary,
    CopyResponse,
    TaskResumeRequest,
    ContentBriefRequest,
    ContentBriefResponse,
)
from app.schemas.common import ApiResponse, PaginationResponse
from app.core.deps import get_current_active_user
from app.utils.log_writer import write_log
from app.utils.logger import logger
from app.services.task_lifecycle_service import set_task_execution_status


router = APIRouter(prefix="/tasks", tags=["文案生成任务"])


@router.put("/{task_id}/brief", response_model=ApiResponse[ContentBriefResponse])
def update_content_brief(
    task_id: int,
    body: ContentBriefRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    brief = body.model_dump()
    required = ("topic", "audience", "goal", "key_points")
    missing = [key for key in required if not brief.get(key)]
    completeness = round((len(required) - len(missing)) / len(required), 2)
    task.content_brief = brief
    task.brief_completeness = completeness
    task.brief_missing_fields = missing
    task.content_status = "brief_ready" if not missing else "brief_missing"
    task.status_reason = None if not missing else f"Brief 缺少：{', '.join(missing)}"
    from datetime import datetime

    task.status_updated_at = datetime.utcnow()
    db.commit()
    return ApiResponse(data=ContentBriefResponse(
        task_id=task.id,
        brief=brief,
        completeness_score=completeness,
        missing_fields=missing,
    ))


def _run_agents_background(task_id: int) -> None:
    db = SessionLocal()
    engine = None
    try:
        # 双引擎切换的唯一接缝：按配置 settings.ORCHESTRATION_ENGINE 取编排引擎并调用。
        # 默认 "native"（自研 AgentOrchestrator），切换为 "langgraph" 即用 LangGraph 引擎；
        # 统一接口 run(db, task_id) -> dict 与历史保持一致，API/前端/事务管理均无需改动。
        from app.config import settings
        from app.orchestration import get_orchestration_engine
        task = db.query(Task).filter(Task.id == task_id).first()
        meta = task.orchestration_meta if task and isinstance(task.orchestration_meta, dict) else {}
        engine_name = "langgraph" if meta.get("execution_mode") else settings.ORCHESTRATION_ENGINE
        engine = get_orchestration_engine(engine_name)
        result = engine.run(db=db, task_id=task_id)
        logger.info(f"后台任务执行完成: task_id={task_id}, success={result.get('success')}")
        write_log(
            db,
            category="task",
            action="task.pipeline_complete",
            message=f"任务 {task_id} 编排完成 success={result.get('success')}",
            task_id=task_id,
            extra={
                "success": result.get("success"),
                "task_mode": result.get("task_mode"),
                "awaiting_human": result.get("awaiting_human"),
            },
            is_success=bool(result.get("success")),
        )
    except Exception as e:
        logger.exception(f"后台任务执行异常: task_id={task_id}")
        write_log(
            db,
            category="task",
            action="task.pipeline_error",
            message=f"任务 {task_id} 编排异常: {str(e)[:200]}",
            task_id=task_id,
            level="ERROR",
            is_success=False,
        )
        # 更新任务状态为失败
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            set_task_execution_status(task, TaskStatus.FAILED, reason=str(e))
            task.error_message = str(e)[:500]
            db.commit()
    finally:
        close = getattr(engine, "close", None)
        if close:
            close()
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
    selected_style_card = None
    style_snapshot = None
    if task_data.style_card_id is not None:
        from sqlalchemy import or_

        selected_style_card = db.query(StyleCard).filter(
            StyleCard.id == task_data.style_card_id,
            StyleCard.status == "active",
            or_(StyleCard.owner_id == current_user.id, StyleCard.owner_id.is_(None)),
        ).first()
        if selected_style_card is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定的风格卡不存在")
        if task_data.platform != TaskPlatform.TOUTIAO:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="风格卡当前仅支持今日头条长文")
        from app.services.style_resolution_service import resolve_style_snapshot

        style_snapshot = resolve_style_snapshot(
            db,
            user_id=current_user.id,
            platform=task_data.platform.value,
            selected_style_card_id=selected_style_card.id,
        )

    # 创建任务记录
    from app.services.orchestration_policy import resolve_execution_mode

    task = Task(
        user_id=current_user.id,
        raw_requirement=task_data.raw_requirement,
        platform=task_data.platform,
        hotlist_id=task_data.hotlist_id,
        status=TaskStatus.PENDING,
        orchestration_meta={
            "execution_mode": task_data.execution_mode,
            "resolved_mode": resolve_execution_mode(task_data.execution_mode),
            "selected_style_card_id": selected_style_card.id if selected_style_card else None,
            "selected_style_card_topic": selected_style_card.topic_cluster if selected_style_card else None,
            "applied_style_snapshot": style_snapshot,
        },
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    write_log(
        db,
        category="task",
        action="task.create",
        message=f"用户 {current_user.username} 创建任务 {task.id}",
        user_id=current_user.id,
        task_id=task.id,
        extra={
            "platform": task_data.platform.value,
            "execution_mode": task_data.execution_mode,
            "style_card_id": task_data.style_card_id,
        },
    )

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


def _resume_task_background(task_id: int, action: str) -> None:
    """后台恢复 awaiting_human 任务。"""
    db = SessionLocal()
    try:
        from app.agents.agentic_runners import resume_agentic_pipeline
        from app.config import settings
        from app.orchestration import get_orchestration_engine

        task = db.query(Task).filter(Task.id == task_id).first()
        meta = task.orchestration_meta if task and isinstance(task.orchestration_meta, dict) else {}
        if meta.get("durability_mode") == "langgraph_sqlite_v1":
            engine = get_orchestration_engine("langgraph")
            try:
                result = engine.resume(
                    db,
                    task_id,
                    thread_id=str(meta["thread_id"]),
                    human_input={"action": action},
                )
            finally:
                close = getattr(engine, "close", None)
                if close:
                    close()
            logger.info(
                f"Durable 任务恢复完成: task_id={task_id}, "
                f"action={action}, success={result.get('success')}"
            )
            return
        mode = meta.get("resolved_mode") or (settings.ORCHESTRATION_MODE or "fixed").strip().lower()
        if mode != "agentic":
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                set_task_execution_status(task, TaskStatus.FAILED, reason="仅 agentic 模式支持恢复")
                task.error_message = "仅 agentic 模式支持恢复"
                db.commit()
            return

        result = resume_agentic_pipeline(db, task_id, action=action)  # type: ignore[arg-type]
        logger.info(f"任务恢复完成: task_id={task_id}, action={action}, success={result.get('success')}")
    except Exception as e:
        logger.exception(f"任务恢复异常: task_id={task_id}")
        db.rollback()
        task = db.query(Task).filter(Task.id == task_id).first()
        meta = task.orchestration_meta if task and isinstance(task.orchestration_meta, dict) else {}
        if task and meta.get("durability_mode") != "langgraph_sqlite_v1":
            set_task_execution_status(task, TaskStatus.FAILED, reason=str(e))
            task.error_message = str(e)[:500]
            db.commit()
    finally:
        db.close()


@router.post(
    "/{task_id}/resume",
    response_model=ApiResponse[TaskResponse],
    summary="恢复等待人工介入的任务",
    description="action: retry | accept_draft | cancel",
)
def resume_task(
    task_id: int,
    body: TaskResumeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TaskResponse]:
    """人工介入后恢复 Agentic 任务。"""
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.user_id == current_user.id,
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务 {task_id} 不存在",
        )

    if task.status != TaskStatus.AWAITING_HUMAN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务状态为 {task.status.value}，无法恢复（需要 awaiting_human）",
        )

    meta = task.orchestration_meta if isinstance(task.orchestration_meta, dict) else {}
    if meta.get("durability_mode") == "langgraph_sqlite_v1":
        if body.action == "retry":
            background_tasks.add_task(_resume_task_background, task.id, "retry")
            return ApiResponse(
                success=True,
                message="恢复请求已接收，请轮询状态",
                data=TaskResponse.model_validate(task),
            )

        from app.orchestration import get_orchestration_engine

        engine = get_orchestration_engine("langgraph")
        try:
            result = engine.resume(
                db,
                task.id,
                thread_id=str(meta["thread_id"]),
                human_input={"action": body.action},
            )
        finally:
            close = getattr(engine, "close", None)
            if close:
                close()
        db.refresh(task)
        return ApiResponse(
            success=result.get("success", False),
            message=result.get("message") or result.get("error") or "任务已恢复",
            data=TaskResponse.model_validate(task),
        )

    if body.action == "cancel":
        from app.agents.agentic_runners import resume_agentic_pipeline

        result = resume_agentic_pipeline(db, task.id, action="cancel")
        db.refresh(task)
        return ApiResponse(
            success=result.get("success", False),
            message=result.get("error") or "任务已取消",
            data=TaskResponse.model_validate(task),
        )

    if body.action == "accept_draft":
        from app.agents.agentic_runners import resume_agentic_pipeline

        result = resume_agentic_pipeline(db, task.id, action="accept_draft")
        db.refresh(task)
        return ApiResponse(
            success=result.get("success", True),
            message=result.get("message") or "已接受初稿",
            data=TaskResponse.model_validate(task),
        )

    # retry
    background_tasks.add_task(_resume_task_background, task.id, "retry")
    db.refresh(task)
    return ApiResponse(
        success=True,
        message="任务已重新执行，请轮询状态",
        data=TaskResponse.model_validate(task),
    )
