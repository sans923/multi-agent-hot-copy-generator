"""历史文案派生索引的 Outbox 写入与有限重试处理。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.memory_index_job import MemoryIndexJob
from app.utils.logger import logger


def enqueue_copy_index(
    db: Session,
    *,
    copy_id: int,
    user_id: int,
    payload: dict[str, Any],
) -> MemoryIndexJob:
    """以 copy_id 幂等创建或刷新索引任务，不阻塞业务保存。"""
    job = (
        db.query(MemoryIndexJob)
        .filter(
            MemoryIndexJob.job_type == "upsert_copy",
            MemoryIndexJob.entity_id == copy_id,
        )
        .first()
    )
    if job is None:
        job = MemoryIndexJob(
            job_type="upsert_copy",
            entity_id=copy_id,
            user_id=user_id,
            payload=payload,
            status="pending",
        )
        db.add(job)
    else:
        job.user_id = user_id
        job.payload = payload
        job.status = "pending"
        job.attempts = 0
        job.locked_at = None
        job.last_error = None
    db.commit()
    db.refresh(job)
    return job


def process_pending_memory_index_jobs(
    db: Session,
    *,
    limit: int = 50,
    max_attempts: int = 3,
    lease_seconds: int = 300,
) -> dict[str, int]:
    """处理一批索引任务；用数据库租约避免多调度器重复消费。"""
    now = datetime.utcnow()
    lease_expired_before = now - timedelta(seconds=max(30, lease_seconds))
    jobs = (
        db.query(MemoryIndexJob)
        .filter(
            or_(
                MemoryIndexJob.status.in_(("pending", "failed")),
                (
                    (MemoryIndexJob.status == "processing")
                    & (MemoryIndexJob.locked_at < lease_expired_before)
                ),
            ),
            MemoryIndexJob.attempts < max_attempts,
        )
        .order_by(MemoryIndexJob.created_at, MemoryIndexJob.id)
        .limit(max(1, min(limit, 200)))
        .all()
    )
    completed = 0
    failed = 0
    processed = 0
    from app.services.embedding_service import upsert_copy_to_chroma

    for job in jobs:
        prior_status = job.status
        prior_attempts = int(job.attempts or 0)
        claimed = (
            db.query(MemoryIndexJob)
            .filter(
                MemoryIndexJob.id == job.id,
                MemoryIndexJob.status == prior_status,
                MemoryIndexJob.attempts == prior_attempts,
            )
            .update(
                {
                    MemoryIndexJob.status: "processing",
                    MemoryIndexJob.attempts: prior_attempts + 1,
                    MemoryIndexJob.locked_at: now,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if claimed != 1:
            continue
        processed += 1
        db.refresh(job)
        try:
            upsert_copy_to_chroma(user_id=job.user_id, **dict(job.payload or {}))
            job.status = "completed"
            job.locked_at = None
            job.last_error = None
            completed += 1
        except Exception as exc:  # 索引是派生数据，失败不能回滚 Copy
            job.status = "failed"
            job.locked_at = None
            job.last_error = str(exc)[:1000]
            failed += 1
            logger.warning(
                f"历史文案索引失败: job_id={job.id}, attempts={job.attempts}, error={exc}"
            )
        db.commit()

    return {"processed": processed, "completed": completed, "failed": failed}


def rebuild_copy_memory_index(
    db: Session,
    *,
    user_id: int | None = None,
) -> dict[str, int]:
    """从关系数据库真源重建终稿索引任务，可按用户缩小维护范围。"""
    from app.models.copy import Copy
    from app.models.task import Task

    query = (
        db.query(Copy, Task.user_id)
        .join(Task, Task.id == Copy.task_id)
        .filter(Copy.is_final.is_(True))
    )
    if user_id is not None:
        query = query.filter(Task.user_id == user_id)
    rows = query.order_by(Copy.id).all()
    queued = 0
    for copy, owner_id in rows:
        enqueue_copy_index(
            db,
            copy_id=copy.id,
            user_id=owner_id,
            payload={
                "copy_id": copy.id,
                "task_id": copy.task_id,
                "content": copy.content,
                "title": copy.title or "",
                "platform": copy.platform or "",
                "tone": copy.tone or "",
                "version": copy.version,
                "is_final": copy.is_final,
                "hot_keywords": copy.hot_keywords or [],
                "review_score": float(copy.review_score or 0),
            },
        )
        queued += 1
    return {"eligible": len(rows), "queued": queued}
