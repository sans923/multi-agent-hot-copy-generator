"""数据库任务队列：持久入队、原子租约认领和有限重试。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Event, Thread
from typing import Any
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.task_execution_job import TaskExecutionJob
from app.utils.logger import logger


def enqueue_task_execution(
    db: Session,
    *,
    task_id: int,
    job_type: str,
    dedupe_key: str,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
    revive_terminal: bool = False,
) -> TaskExecutionJob:
    """按稳定业务键幂等入队；唯一键冲突通过 savepoint 安全收敛。"""
    existing = (
        db.query(TaskExecutionJob)
        .filter(TaskExecutionJob.dedupe_key == dedupe_key)
        .first()
    )
    if existing is not None:
        if revive_terminal and existing.status == "dead":
            updated = db.query(TaskExecutionJob).filter(
                TaskExecutionJob.id == existing.id,
                TaskExecutionJob.status == "dead",
            ).update(
                {
                    TaskExecutionJob.status: "pending",
                    TaskExecutionJob.attempts: 0,
                    TaskExecutionJob.available_at: datetime.utcnow(),
                    TaskExecutionJob.locked_at: None,
                    TaskExecutionJob.worker_id: None,
                    TaskExecutionJob.lease_token: None,
                    TaskExecutionJob.last_error: None,
                    TaskExecutionJob.payload: payload or {},
                },
                synchronize_session=False,
            )
            if commit:
                db.commit()
            else:
                db.flush()
            db.expire_all()
            if updated == 0 and commit:
                # 结束旧快照后返回当前认领状态，绝不覆盖 processing 租约。
                db.rollback()
            return db.query(TaskExecutionJob).filter_by(id=existing.id).one()
        return existing

    job = TaskExecutionJob(
        task_id=task_id,
        job_type=job_type,
        dedupe_key=dedupe_key,
        payload=payload or {},
        status="pending",
        available_at=datetime.utcnow(),
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        # MySQL 默认 REPEATABLE READ 下，首次查询建立的快照看不到并发事务
        # 刚提交的唯一键记录；结束外层事务后再查才能稳定收敛到现有 Job。
        if not commit:
            raise
        db.rollback()
        existing = (
            db.query(TaskExecutionJob)
            .filter(TaskExecutionJob.dedupe_key == dedupe_key)
            .one_or_none()
        )
        if existing is None:
            raise
        return existing

    if commit:
        db.commit()
        db.refresh(job)
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

    # 最后一次尝试的 Worker 崩溃后，过期 Job 不应永久卡在 processing。
    db.query(TaskExecutionJob).filter(
        TaskExecutionJob.status == "processing",
        TaskExecutionJob.attempts >= max_attempts,
        TaskExecutionJob.locked_at < lease_expired_before,
    ).update(
        {
            TaskExecutionJob.status: "dead",
            TaskExecutionJob.locked_at: None,
            TaskExecutionJob.worker_id: None,
            TaskExecutionJob.lease_token: None,
            TaskExecutionJob.last_error: "最终尝试的 Worker 租约过期",
        },
        synchronize_session=False,
    )
    db.commit()

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
                    TaskExecutionJob.lease_token: str(uuid4()),
                    TaskExecutionJob.last_error: None,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if updated == 1:
            return db.query(TaskExecutionJob).filter_by(id=candidate.id).one()
        db.expire_all()


def renew_task_execution_lease(
    db: Session,
    job_id: int,
    lease_token: str,
    attempt: int,
    *,
    now: datetime | None = None,
) -> bool:
    """只允许当前认领者续租；token + attempt 共同充当 fencing token。"""
    updated = db.query(TaskExecutionJob).filter(
        TaskExecutionJob.id == job_id,
        TaskExecutionJob.status == "processing",
        TaskExecutionJob.lease_token == lease_token,
        TaskExecutionJob.attempts == attempt,
    ).update(
        {TaskExecutionJob.locked_at: now or datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()
    return updated == 1


def mark_task_execution_completed(
    db: Session,
    job_id: int,
    lease_token: str,
    attempt: int,
) -> bool:
    updated = db.query(TaskExecutionJob).filter(
        TaskExecutionJob.id == job_id,
        TaskExecutionJob.status == "processing",
        TaskExecutionJob.lease_token == lease_token,
        TaskExecutionJob.attempts == attempt,
    ).update(
        {
            TaskExecutionJob.status: "completed",
            TaskExecutionJob.locked_at: None,
            TaskExecutionJob.worker_id: None,
            TaskExecutionJob.lease_token: None,
            TaskExecutionJob.last_error: None,
        },
        synchronize_session=False,
    )
    db.commit()
    return updated == 1


def mark_task_execution_failed(
    db: Session,
    job_id: int,
    lease_token: str,
    attempt: int,
    error: Exception,
    *,
    max_attempts: int = 3,
    retry_delay_seconds: int = 5,
) -> bool:
    updated = db.query(TaskExecutionJob).filter(
        TaskExecutionJob.id == job_id,
        TaskExecutionJob.status == "processing",
        TaskExecutionJob.lease_token == lease_token,
        TaskExecutionJob.attempts == attempt,
    ).update(
        {
            TaskExecutionJob.status: "dead" if attempt >= max_attempts else "pending",
            TaskExecutionJob.available_at: datetime.utcnow()
            + timedelta(seconds=max(0, retry_delay_seconds)),
            TaskExecutionJob.locked_at: None,
            TaskExecutionJob.worker_id: None,
            TaskExecutionJob.lease_token: None,
            TaskExecutionJob.last_error: str(error)[:1000],
        },
        synchronize_session=False,
    )
    db.commit()
    return updated == 1


def process_one_task_execution_job(
    db: Session,
    *,
    worker_id: str,
    execute: Callable[[TaskExecutionJob], None],
    lease_seconds: int = 300,
    max_attempts: int = 3,
    retry_delay_seconds: int = 5,
    heartbeat_session_factory: Callable[[], Session] | None = None,
    heartbeat_interval_seconds: float | None = None,
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
    lease_token = str(job.lease_token)
    attempt = int(job.attempts)
    stop_heartbeat = Event()
    lease_lost = Event()
    # 仅运行时属性：让编排层所有 Session 共享即时失租信号。
    job._lease_lost_event = lease_lost
    heartbeat_thread = None
    if heartbeat_session_factory is not None:
        interval = heartbeat_interval_seconds or max(1.0, lease_seconds / 3)

        def heartbeat() -> None:
            while not stop_heartbeat.wait(interval):
                try:
                    heartbeat_db = heartbeat_session_factory()
                    try:
                        renewed = renew_task_execution_lease(
                            heartbeat_db, job.id, lease_token, attempt
                        )
                    finally:
                        heartbeat_db.close()
                    if not renewed:
                        lease_lost.set()
                        return
                except Exception:
                    logger.exception(
                        f"任务租约续期失败: job_id={job.id}, attempt={attempt}"
                    )
                    lease_lost.set()
                    return

        heartbeat_thread = Thread(target=heartbeat, daemon=True)
        heartbeat_thread.start()
    execution_error = None
    try:
        execute(job)
    except Exception as exc:
        execution_error = exc
    finally:
        stop_heartbeat.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1)

    if execution_error is not None:
        updated = mark_task_execution_failed(
            db,
            job.id,
            lease_token,
            attempt,
            execution_error,
            max_attempts=max_attempts,
            retry_delay_seconds=retry_delay_seconds,
        )
        if not updated:
            logger.error(f"忽略已失效执行的失败写回: job_id={job.id}")
    else:
        updated = mark_task_execution_completed(db, job.id, lease_token, attempt)
        if not updated:
            logger.error(f"忽略已失效执行的完成写回: job_id={job.id}")
        elif lease_lost.is_set():
            logger.warning(
                f"heartbeat 状态未知，但 fencing CAS 确认当前租约后完成: job_id={job.id}"
            )
    return True
