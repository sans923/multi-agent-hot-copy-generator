"""持久任务执行队列：幂等入队、原子认领、租约恢复和失败重试。"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.api.v1.tasks import create_task
from app.models.task import Task, TaskPlatform
from app.models.task_execution_job import TaskExecutionJob
from app.models.user import User
from app.schemas.task import TaskCreate
from app.services.task_execution_queue import (
    claim_task_execution_job,
    enqueue_task_execution,
    mark_task_execution_completed,
    mark_task_execution_failed,
    process_one_task_execution_job,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    user = User(username="queue-user", email="queue@example.com", hashed_password="hashed")
    session.add(user)
    session.flush()
    task = Task(user_id=user.id, raw_requirement="生成文案", platform=TaskPlatform.WEIBO)
    session.add(task)
    session.commit()
    try:
        yield session, task
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_enqueue_is_persistent_and_idempotent(db):
    session, task = db

    first = enqueue_task_execution(
        session,
        task_id=task.id,
        job_type="start",
        dedupe_key=f"start:{task.id}",
    )
    second = enqueue_task_execution(
        session,
        task_id=task.id,
        job_type="start",
        dedupe_key=f"start:{task.id}",
    )

    assert first.id == second.id
    assert session.query(TaskExecutionJob).count() == 1
    assert first.status == "pending"


def test_job_can_only_be_claimed_once(db):
    session, task = db
    enqueue_task_execution(
        session, task_id=task.id, job_type="start", dedupe_key=f"start:{task.id}"
    )

    claimed = claim_task_execution_job(session, worker_id="worker-a")

    assert claimed is not None
    assert claimed.status == "processing"
    assert claimed.worker_id == "worker-a"
    assert claimed.attempts == 1
    assert claim_task_execution_job(session, worker_id="worker-b") is None


def test_expired_processing_lease_is_reclaimed(db):
    session, task = db
    job = enqueue_task_execution(
        session, task_id=task.id, job_type="start", dedupe_key=f"start:{task.id}"
    )
    job.status = "processing"
    job.attempts = 1
    job.worker_id = "dead-worker"
    job.locked_at = datetime.utcnow() - timedelta(minutes=10)
    session.commit()

    claimed = claim_task_execution_job(
        session, worker_id="replacement", lease_seconds=60
    )

    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.worker_id == "replacement"
    assert claimed.attempts == 2


def test_failed_job_retries_then_becomes_dead(db):
    session, task = db
    enqueue_task_execution(
        session, task_id=task.id, job_type="start", dedupe_key=f"start:{task.id}"
    )
    claimed = claim_task_execution_job(session, worker_id="worker-a", max_attempts=2)
    assert claimed is not None

    mark_task_execution_failed(
        session, claimed.id, RuntimeError("temporary"), max_attempts=2, retry_delay_seconds=0
    )
    retried = claim_task_execution_job(session, worker_id="worker-b", max_attempts=2)
    assert retried is not None
    mark_task_execution_failed(
        session, retried.id, RuntimeError("permanent"), max_attempts=2, retry_delay_seconds=0
    )

    session.refresh(retried)
    assert retried.status == "dead"
    assert retried.last_error == "permanent"
    assert claim_task_execution_job(session, worker_id="worker-c", max_attempts=2) is None


def test_completed_job_releases_its_lease(db):
    session, task = db
    enqueue_task_execution(
        session, task_id=task.id, job_type="start", dedupe_key=f"start:{task.id}"
    )
    claimed = claim_task_execution_job(session, worker_id="worker-a")
    assert claimed is not None

    mark_task_execution_completed(session, claimed.id)

    session.refresh(claimed)
    assert claimed.status == "completed"
    assert claimed.worker_id is None
    assert claimed.locked_at is None


def test_worker_processes_one_persisted_job(db):
    session, task = db
    enqueue_task_execution(
        session, task_id=task.id, job_type="start", dedupe_key=f"start:{task.id}"
    )
    seen: list[tuple[str, int]] = []

    processed = process_one_task_execution_job(
        session,
        worker_id="worker-a",
        execute=lambda job: seen.append((job.job_type, job.task_id)),
    )

    assert processed is True
    assert seen == [("start", task.id)]
    job = session.query(TaskExecutionJob).one()
    assert job.status == "completed"


def test_create_task_persists_job_without_fastapi_background_task(db):
    session, existing_task = db
    user = session.query(User).filter_by(id=existing_task.user_id).one()

    response = create_task(
        TaskCreate(raw_requirement="新的持久任务", platform=TaskPlatform.WEIBO),
        current_user=user,
        db=session,
    )

    job = session.query(TaskExecutionJob).filter_by(task_id=response.data.id).one()
    assert job.job_type == "start"
    assert job.status == "pending"
    assert job.dedupe_key == f"start:{response.data.id}"
