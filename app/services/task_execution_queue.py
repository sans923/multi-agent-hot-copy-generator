"""数据库任务队列：持久入队、原子租约认领和有限重试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from collections.abc import Callable
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.task_execution_job import TaskExecutionJob


def enqueue_task_execution(
    db: Session,
    *,
    task_id: int,
    job_type: str,
    dedupe_key: str,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
) -> TaskExecutionJob:
    """按稳定业务键幂等入队；commit=False 可与 Task 创建同事务提交。"""
    existing = (
        db.query(TaskExecutionJob)
        .filter(TaskExecutionJob.dedupe_key == dedupe_key)
        .first()
    )
    if existing is not None:
        return existing

    job = TaskExecutionJob(
        task_id=task_id,
        job_type=job_type,
        dedupe_key=dedupe_key,
        payload=payload or {},
        status="pending",
        available_at=datetime.utcnow(),
    )
    db.add(job)
    if commit:
        db.commit()
        db.refresh(job)
    else:
        db.flush()
    return job


def claim_task_execution_job(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = 300,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> TaskExecutionJob | None:
    """条件更新认领一个 Job；并发 Worker 中只有一个能更新成功。"""
    claim_time = now or datetime.utcnow()
    lease_expired_before = claim_time - timedelta(seconds=max(1, lease_seconds))

    while True:
        candidate = (
            db.query(TaskExecutionJob)
            .filter(
                TaskExecutionJob.attempts < max_attempts,
                or_(
                    (
                        (TaskExecutionJob.status == "pending")
                        & (TaskExecutionJob.available_at <= claim_time)
                    ),
                    (
                        (TaskExecutionJob.status == "processing")
                        & (TaskExecutionJob.locked_at < lease_expired_before)
                    ),
                ),
            )
            .order_by(TaskExecutionJob.available_at, TaskExecutionJob.id)
            .first()
        )
        if candidate is None:
            return None

        prior_status = candidate.status
        prior_attempts = int(candidate.attempts or 0)
        updated = (
            db.query(TaskExecutionJob)
            .filter(
                TaskExecutionJob.id == candidate.id,
                TaskExecutionJob.status == prior_status,
                TaskExecutionJob.attempts == prior_attempts,
            )
            .update(
                {
                    TaskExecutionJob.status: "processing",
                    TaskExecutionJob.attempts: prior_attempts + 1,
                    TaskExecutionJob.locked_at: claim_time,
                    TaskExecutionJob.worker_id: worker_id,
                    TaskExecutionJob.last_error: None,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if updated == 1:
            return db.query(TaskExecutionJob).filter_by(id=candidate.id).one()
        db.expire_all()


def mark_task_execution_completed(db: Session, job_id: int) -> None:
    job = db.query(TaskExecutionJob).filter_by(id=job_id).one()
    job.status = "completed"
    job.locked_at = None
    job.worker_id = None
    job.last_error = None
    db.commit()


def mark_task_execution_failed(
    db: Session,
    job_id: int,
    error: Exception,
    *,
    max_attempts: int = 3,
    retry_delay_seconds: int = 5,
) -> None:
    job = db.query(TaskExecutionJob).filter_by(id=job_id).one()
    job.status = "dead" if int(job.attempts or 0) >= max_attempts else "pending"
    job.available_at = datetime.utcnow() + timedelta(
        seconds=max(0, retry_delay_seconds)
    )
    job.locked_at = None
    job.worker_id = None
    job.last_error = str(error)[:1000]
    db.commit()


def process_one_task_execution_job(
    db: Session,
    *,
    worker_id: str,
    execute: Callable[[TaskExecutionJob], None],
    lease_seconds: int = 300,
    max_attempts: int = 3,
    retry_delay_seconds: int = 5,
) -> bool:
    """认领并执行一个 Job；业务异常进入有限重试而不会退出 Worker。"""
    job = claim_task_execution_job(
        db,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        max_attempts=max_attempts,
    )
    if job is None:
        return False
    try:
        execute(job)
    except Exception as exc:
        mark_task_execution_failed(
            db,
            job.id,
            exc,
            max_attempts=max_attempts,
            retry_delay_seconds=retry_delay_seconds,
        )
    else:
        mark_task_execution_completed(db, job.id)
    return True
