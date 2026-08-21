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
    renew_task_execution_lease,
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
        session,
        claimed.id,
        claimed.lease_token,
        claimed.attempts,
        RuntimeError("temporary"),
        max_attempts=2,
        retry_delay_seconds=0,
    )
    retried = claim_task_execution_job(session, worker_id="worker-b", max_attempts=2)
    assert retried is not None
    mark_task_execution_failed(
        session,
        retried.id,
        retried.lease_token,
        retried.attempts,
        RuntimeError("permanent"),
        max_attempts=2,
        retry_delay_seconds=0,
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

    completed = mark_task_execution_completed(
        session, claimed.id, claimed.lease_token, claimed.attempts
    )

    assert completed is True
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


def test_stale_worker_cannot_overwrite_reclaimed_job(db):
    session, task = db
    job = enqueue_task_execution(
        session, task_id=task.id, job_type="start", dedupe_key=f"start:{task.id}"
    )
    first = claim_task_execution_job(session, worker_id="worker-a", lease_seconds=1)
    assert first is not None
    first_token = first.lease_token
    first_attempt = first.attempts
    first.locked_at = datetime.utcnow() - timedelta(minutes=1)
    session.commit()

    second = claim_task_execution_job(session, worker_id="worker-b", lease_seconds=1)
    assert second is not None
    assert second.lease_token != first_token

    assert mark_task_execution_completed(
        session, job.id, first_token, first_attempt
    ) is False
    session.refresh(second)
    assert second.status == "processing"
    assert second.worker_id == "worker-b"


def test_lease_heartbeat_requires_current_fencing_token(db):
    session, task = db
    enqueue_task_execution(
        session, task_id=task.id, job_type="start", dedupe_key=f"start:{task.id}"
    )
    claimed = claim_task_execution_job(session, worker_id="worker-a")
    assert claimed is not None
    old_locked_at = claimed.locked_at

    assert renew_task_execution_lease(
        session, claimed.id, "stale-token", claimed.attempts
    ) is False
    assert renew_task_execution_lease(
        session,
        claimed.id,
        claimed.lease_token,
        claimed.attempts,
        now=old_locked_at + timedelta(seconds=10),
    ) is True
    session.refresh(claimed)
    assert claimed.locked_at == old_locked_at + timedelta(seconds=10)


def test_expired_final_attempt_is_reaped_as_dead(db):
    session, task = db
    job = enqueue_task_execution(
        session, task_id=task.id, job_type="start", dedupe_key=f"start:{task.id}"
    )
    job.status = "processing"
    job.attempts = 3
    job.worker_id = "crashed-worker"
    job.lease_token = "expired-token"
    job.locked_at = datetime.utcnow() - timedelta(minutes=10)
    session.commit()

    assert claim_task_execution_job(
        session, worker_id="replacement", lease_seconds=60, max_attempts=3
    ) is None
    session.refresh(job)
    assert job.status == "dead"
    assert "租约过期" in job.last_error


def test_dead_human_retry_job_can_be_revived(db):
    session, task = db
    job = enqueue_task_execution(
        session,
        task_id=task.id,
        job_type="resume",
        dedupe_key=f"resume:{task.id}:retry:v1",
        payload={"action": "retry"},
    )
    job.status = "dead"
    job.attempts = 3
    job.last_error = "temporary outage"
    session.commit()

    revived = enqueue_task_execution(
        session,
        task_id=task.id,
        job_type="resume",
        dedupe_key=job.dedupe_key,
        payload={"action": "retry"},
        revive_terminal=True,
    )

    assert revived.id == job.id
    assert revived.status == "pending"
    assert revived.attempts == 0
    assert revived.last_error is None


def test_stale_dead_reviver_cannot_overwrite_a_new_claim(db):
    session, task = db
    job = enqueue_task_execution(
        session,
        task_id=task.id,
        job_type="resume",
        dedupe_key=f"resume:{task.id}:retry:race",
    )
    job.status = "dead"
    job.attempts = 3
    session.commit()

    second_session = sessionmaker(bind=session.get_bind(), autoflush=False)()
    second_session.query(TaskExecutionJob).filter_by(id=job.id).one()
    enqueue_task_execution(
        session,
        task_id=task.id,
        job_type="resume",
        dedupe_key=job.dedupe_key,
        revive_terminal=True,
    )
    claimed = claim_task_execution_job(session, worker_id="new-owner")
    assert claimed is not None

    observed = enqueue_task_execution(
        second_session,
        task_id=task.id,
        job_type="resume",
        dedupe_key=job.dedupe_key,
        revive_terminal=True,
    )

    assert observed.status == "processing"
    assert observed.worker_id == "new-owner"
    assert observed.lease_token == claimed.lease_token
    second_session.close()


def test_heartbeat_failure_uses_fenced_ack_when_token_is_still_current(db):
    session, task = db
    enqueue_task_execution(
        session, task_id=task.id, job_type="start", dedupe_key=f"start:{task.id}"
    )

    def broken_session_factory():
        raise RuntimeError("database unavailable")

    processed = process_one_task_execution_job(
        session,
        worker_id="worker-a",
        execute=lambda _job: __import__("time").sleep(0.03),
        heartbeat_session_factory=broken_session_factory,
        heartbeat_interval_seconds=0.01,
    )

    assert processed is True
    session.expire_all()
    job = session.query(TaskExecutionJob).one()
    assert job.status == "completed"
