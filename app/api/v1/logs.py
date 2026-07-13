"""
日志查询接口（/api/v1/logs）
==============================
提供 3 个查询接口：

1. GET /api/v1/logs/agent   - 查 Agent Skill 调用记录
   用途：调试Agent行为，看哪个Skill被调用、参数和结果是什么
   权限：需要登录，只能查自己任务的日志（管理员可查所有）

2. GET /api/v1/logs/tasks   - 查任务执行汇总
   用途：了解任务完成情况，统计成功率/平均得分/token消耗
   权限：需要登录，只能查自己的任务

3. GET /api/v1/logs/system  - 查系统操作日志
   用途：安全审计/运维监控
   权限：仅管理员

【面试加分点】
这 3 个接口是整个系统的"可观测性"（Observability）入口，
在面试中可以说：
"系统有完整的可观测性设计：
 - Agent每次Skill调用都有详细日志（agent_logs表）
 - 系统级操作有审计日志（system_logs表）
 - 提供3个查询API供运维和调试使用"
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_

from app.database import get_db
from app.models.orchestration_audit_log import OrchestrationAuditLog
from app.models.agent_log import AgentLog
from app.models.task import Task, TaskStatus
from app.models.copy import Copy
from app.models.system_log import SystemLog
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationResponse
from app.core.deps import get_current_active_user, get_current_admin_user
from app.utils.logger import logger


router = APIRouter(prefix="/logs", tags=["日志查询"])


# ====================================================
# 接口 0：全链路编排审计时间线
# ====================================================

@router.get(
    "/audit",
    response_model=ApiResponse,
    summary="查询任务全链路审计时间线",
    description="按 sequence_no 排序，覆盖编排/Skill/LLM/验证/Judge/人工介入等每一步。",
)
def get_audit_trail(
    task_id: int = Query(..., description="任务ID"),
    step_type: Optional[str] = Query(None, description="步骤类型过滤"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """查询 orchestration_audit_logs，构建可展示的执行轨迹。"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return ApiResponse(success=False, message=f"任务 {task_id} 不存在", data=None)

    if not current_user.is_admin and task.user_id != current_user.id:
        return ApiResponse(success=False, message="无权查看该任务审计日志", data=None)

    query = db.query(OrchestrationAuditLog).filter(
        OrchestrationAuditLog.task_id == task_id
    )
    if step_type:
        query = query.filter(OrchestrationAuditLog.step_type == step_type)

    logs = query.order_by(OrchestrationAuditLog.sequence_no.asc()).all()

    items = [
        {
            "id": log.id,
            "task_id": log.task_id,
            "sequence_no": log.sequence_no,
            "step_type": log.step_type,
            "step_name": log.step_name,
            "agent_name": log.agent_name,
            "input_summary": log.input_summary,
            "output_summary": log.output_summary,
            "status": log.status,
            "failure_level": log.failure_level,
            "duration_ms": log.duration_ms,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    type_stats = (
        db.query(OrchestrationAuditLog.step_type, func.count(OrchestrationAuditLog.id))
        .filter(OrchestrationAuditLog.task_id == task_id)
        .group_by(OrchestrationAuditLog.step_type)
        .all()
    )

    return ApiResponse(
        success=True,
        message=f"共 {len(items)} 条审计记录",
        data={
            "task_id": task_id,
            "total": len(items),
            "type_statistics": {t: c for t, c in type_stats},
            "items": items,
        },
    )


# ====================================================
# 接口 1：Agent Skill 调用记录
# ====================================================

@router.get(
    "/agent",
    response_model=ApiResponse,
    summary="查询 Agent Skill 调用记录",
    description="查看 Agent 每次调用哪个 Skill、参数是什么、结果如何。调试Agent行为用。"
)
def get_agent_logs(
    task_id: Optional[int] = Query(None, description="按任务ID过滤"),
    agent_name: Optional[str] = Query(None, description="按Agent名称过滤: requirement_agent/copywriter_agent/reviewer_agent"),
    skill_name: Optional[str] = Query(None, description="按Skill名称过滤"),
    status: Optional[str] = Query(None, description="按状态过滤: success/failed"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    查询 agent_logs 表
    
    返回示例：
    {
      "items": [
        {
          "id": 1,
          "task_id": 5,
          "agent_name": "copywriter_agent",
          "skill_name": "generate_outline",
          "skill_input": {"topic": "AI技术", "platform": "weibo"},
          "skill_output": {"success": true, "outline": {...}},
          "status": "success",
          "duration_seconds": 0.8,
          "tokens_used": 0,
          "created_at": "2026-04-27T10:00:00"
        }
      ],
      "total": 42
    }
    """
    # 构建基础查询
    query = db.query(AgentLog)

    # 非管理员只能查自己任务的日志
    if not current_user.is_admin:
        # 通过 task -> user 过滤
        user_task_ids = db.query(Task.id).filter(Task.user_id == current_user.id).subquery()
        query = query.filter(AgentLog.task_id.in_(user_task_ids))

    # 应用过滤条件
    if task_id:
        query = query.filter(AgentLog.task_id == task_id)
    if agent_name:
        query = query.filter(AgentLog.agent_name == agent_name)
    if skill_name:
        query = query.filter(AgentLog.skill_name == skill_name)
    if status:
        query = query.filter(AgentLog.status == status)

    total = query.count()
    logs = (
        query
        .order_by(desc(AgentLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        {
            "id": log.id,
            "task_id": log.task_id,
            "agent_name": log.agent_name,
            "skill_name": log.skill_name,
            "skill_input": log.skill_input,
            "skill_output": log.skill_output,
            "status": log.status,
            "duration_seconds": log.duration_seconds,
            "tokens_used": log.tokens_used,
            "error_message": log.error_message,
            "iteration": log.iteration,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    logger.info(f"查询Agent日志: user_id={current_user.id}, total={total}")

    return ApiResponse(
        success=True,
        message=f"共 {total} 条记录",
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    )


# ====================================================
# 接口 2：任务执行汇总
# ====================================================

@router.get(
    "/tasks",
    response_model=ApiResponse,
    summary="查询任务执行汇总",
    description="查看任务完成情况，包含各阶段Agent的执行统计"
)
def get_task_logs(
    status: Optional[str] = Query(None, description="按任务状态过滤: pending/processing/completed/failed"),
    start_date: Optional[str] = Query(None, description="开始日期，格式 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    查询任务执行汇总，每条记录包含：
    - 任务基本信息（ID/需求/平台/状态）
    - 生成的文案数量和最终得分
    - 消耗的 token 统计
    - 执行耗时
    """
    query = db.query(Task)

    # 非管理员只能查自己的任务
    if not current_user.is_admin:
        query = query.filter(Task.user_id == current_user.id)

    if status:
        try:
            query = query.filter(Task.status == TaskStatus(status))
        except ValueError:
            pass

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(Task.created_at >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Task.created_at < end_dt)
        except ValueError:
            pass

    total = query.count()
    tasks = (
        query
        .order_by(desc(Task.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for task in tasks:
        # 查该任务的文案统计
        copy_stats = (
            db.query(
                func.count(Copy.id).label("copy_count"),
                func.max(Copy.review_score).label("best_score"),
                func.sum(Copy.tokens_used).label("total_tokens"),
            )
            .filter(Copy.task_id == task.id)
            .first()
        )

        # 查该任务的 Agent 调用次数
        agent_call_count = (
            db.query(func.count(AgentLog.id))
            .filter(AgentLog.task_id == task.id)
            .scalar()
        )

        items.append({
            "task_id": task.id,
            "platform": task.platform.value if task.platform else "",
            "status": task.status.value if task.status else "",
            "raw_requirement": task.raw_requirement[:50] + "..." if len(task.raw_requirement) > 50 else task.raw_requirement,
            "copy_count": copy_stats.copy_count if copy_stats else 0,
            "best_review_score": copy_stats.best_score if copy_stats else None,
            "total_tokens_used": copy_stats.total_tokens if copy_stats else 0,
            "agent_skill_calls": agent_call_count or 0,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        })

    # 统计概览数据
    overview = _get_task_overview(db, current_user)

    return ApiResponse(
        success=True,
        message=f"共 {total} 条任务记录",
        data={
            "overview": overview,
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    )


def _get_task_overview(db: Session, user: User) -> dict:
    """计算任务统计概览"""
    base_query = db.query(Task)
    if not user.is_admin:
        base_query = base_query.filter(Task.user_id == user.id)

    total = base_query.count()
    completed = base_query.filter(Task.status == TaskStatus.COMPLETED).count()
    failed = base_query.filter(Task.status == TaskStatus.FAILED).count()
    pending = base_query.filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING])).count()

    # 平均审核得分
    avg_score = (
        db.query(func.avg(Copy.review_score))
        .join(Task, Copy.task_id == Task.id)
        .filter(Copy.review_score.isnot(None))
    )
    if not user.is_admin:
        avg_score = avg_score.filter(Task.user_id == user.id)
    avg_score = avg_score.scalar()

    return {
        "total_tasks": total,
        "completed": completed,
        "failed": failed,
        "pending_or_processing": pending,
        "success_rate": f"{round(completed / total * 100, 1)}%" if total > 0 else "0%",
        "avg_review_score": round(float(avg_score), 1) if avg_score else None,
    }


# ====================================================
# 接口 3：系统操作日志（仅管理员）
# ====================================================

@router.get(
    "/system",
    response_model=ApiResponse,
    summary="查询系统操作日志（管理员）",
    description="查看用户登录/注册、热榜同步、系统事件等操作记录。仅管理员可访问。"
)
def get_system_logs(
    category: Optional[str] = Query(None, description="日志分类: auth/task/hotlist/agent/system"),
    level: Optional[str] = Query(None, description="日志级别: INFO/WARNING/ERROR"),
    user_id: Optional[int] = Query(None, description="按用户ID过滤"),
    is_success: Optional[bool] = Query(None, description="是否成功"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_admin: User = Depends(get_current_admin_user),  # 仅管理员
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    查询 system_logs 表（管理员专用）
    
    典型使用场景：
    - 查看过去1小时的 ERROR 级别日志：level=ERROR
    - 查看某用户的所有操作：user_id=123
    - 查看热榜同步情况：category=hotlist
    - 查看失败的操作：is_success=false
    """
    query = db.query(SystemLog)

    if category:
        query = query.filter(SystemLog.category == category)
    if level:
        query = query.filter(SystemLog.level == level.upper())
    if user_id:
        query = query.filter(SystemLog.user_id == user_id)
    if is_success is not None:
        query = query.filter(SystemLog.is_success == (1 if is_success else 0))

    if start_date:
        try:
            query = query.filter(
                SystemLog.created_at >= datetime.strptime(start_date, "%Y-%m-%d")
            )
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(SystemLog.created_at < end_dt)
        except ValueError:
            pass

    total = query.count()
    logs = (
        query
        .order_by(desc(SystemLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 统计各级别日志数量（用于图表展示）
    level_stats = (
        db.query(SystemLog.level, func.count(SystemLog.id))
        .group_by(SystemLog.level)
        .all()
    )

    items = [
        {
            "id": log.id,
            "level": log.level,
            "category": log.category,
            "action": log.action,
            "message": log.message,
            "user_id": log.user_id,
            "task_id": log.task_id,
            "extra": log.extra,
            "ip_address": log.ip_address,
            "duration_ms": log.duration_ms,
            "is_success": bool(log.is_success),
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    return ApiResponse(
        success=True,
        message=f"共 {total} 条系统日志",
        data={
            "level_statistics": {level: count for level, count in level_stats},
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    )
