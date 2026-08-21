"""历史文案派生索引的 Outbox 写入与有限重试处理。"""

from __future__ import annotations

from typing import Any

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
        job.last_error = None
    db.commit()
    db.refresh(job)
    return job


def process_pending_memory_index_jobs(
    db: Session,
    *,
    limit: int = 50,
    max_attempts: int = 3,
) -> dict[str, int]:
    """处理一批索引任务；失败保留证据，未超上限的任务可再次执行。"""
    jobs = (
        db.query(MemoryIndexJob)
        .filter(
            MemoryIndexJob.status.in_(("pending", "failed")),
            MemoryIndexJob.attempts < max_attempts,
        )
        .order_by(MemoryIndexJob.created_at, MemoryIndexJob.id)
        .limit(max(1, min(limit, 200)))
        .all()
    )
    completed = 0
    failed = 0
    from app.services.embedding_service import upsert_copy_to_chroma

    for job in jobs:
        job.attempts = int(job.attempts or 0) + 1
        try:
            upsert_copy_to_chroma(user_id=job.user_id, **dict(job.payload or {}))
            job.status = "completed"
            job.last_error = None
            completed += 1
        except Exception as exc:  # 索引是派生数据，失败不能回滚 Copy
            job.status = "failed"
            job.last_error = str(exc)[:1000]
            failed += 1
            logger.warning(
                f"历史文案索引失败: job_id={job.id}, attempts={job.attempts}, error={exc}"
            )
        db.commit()

    return {"processed": len(jobs), "completed": completed, "failed": failed}
