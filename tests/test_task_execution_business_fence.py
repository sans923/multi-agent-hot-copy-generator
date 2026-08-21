import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.tasks import (
    TaskExecutionLeaseLost,
    _install_task_execution_lease_guard,
)
from app.database import Base
from app.models.task import Task, TaskPlatform
from app.models.task_execution_job import TaskExecutionJob
from app.models.user import User


@pytest.fixture()
def fenced_sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fence.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    setup = factory()
    user = User(username="fence", email="fence@example.com", hashed_password="hash")
    setup.add(user)
    setup.flush()
    task = Task(user_id=user.id, raw_requirement="fence", platform=TaskPlatform.WEIBO)
    setup.add(task)
    setup.flush()
    job = TaskExecutionJob(
        task_id=task.id,
        job_type="start",
        dedupe_key="fence:start",
        status="processing",
        attempts=1,
        worker_id="old",
        lease_token="old-token",
    )
    setup.add(job)
    setup.commit()
    ids = task.id, job.id
    setup.close()
    try:
        yield factory, ids
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_stale_lease_blocks_orm_flush(fenced_sessions):
    factory, (task_id, job_id) = fenced_sessions
    business = factory()
    _install_task_execution_lease_guard(business, job_id, "old-token", 1)

    owner = factory()
    owner.query(TaskExecutionJob).filter_by(id=job_id).update(
        {TaskExecutionJob.lease_token: "new-token", TaskExecutionJob.worker_id: "new"}
    )
    owner.commit()
    owner.close()

    task = business.query(Task).filter_by(id=task_id).one()
    task.raw_requirement = "stale write"
    with pytest.raises(TaskExecutionLeaseLost):
        business.commit()
    business.rollback()
    business.close()


def test_stale_lease_blocks_bulk_update(fenced_sessions):
    factory, (task_id, job_id) = fenced_sessions
    business = factory()
    _install_task_execution_lease_guard(business, job_id, "old-token", 1)

    owner = factory()
    owner.query(TaskExecutionJob).filter_by(id=job_id).update(
        {TaskExecutionJob.status: "dead", TaskExecutionJob.lease_token: None}
    )
    owner.commit()
    owner.close()

    with pytest.raises(TaskExecutionLeaseLost):
        business.query(Task).filter_by(id=task_id).update({Task.raw_requirement: "stale"})
    business.rollback()
    business.close()
