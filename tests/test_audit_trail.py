"""
编排审计日志测试
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.task import Task, TaskPlatform, TaskStatus
from app.models.user import User
from app.models.orchestration_audit_log import OrchestrationAuditLog
from app.services.audit_service import write_audit_log, audit_step
from app.skills.base import SkillExecutor, SkillRegistry
from app.skills.compliance_skills import CheckSensitiveWordsSkill


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_database():
    from app.models import user, task, document, copy, agent_log, hotlist_sync  # noqa: F401
    from app.models import orchestration_audit_log  # noqa: F401

    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _create_task(db) -> Task:
    user = User(username="audit_user", email="a@x.com", hashed_password="h")
    db.add(user)
    db.commit()
    task = Task(
        user_id=user.id,
        raw_requirement="测试",
        platform=TaskPlatform.WEIBO,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_write_audit_log_sequence(db):
    task = _create_task(db)
    write_audit_log(db, task.id, "orchestration", "pipeline_start")
    write_audit_log(db, task.id, "stage", "requirement_start", agent_name="requirement_agent")

    logs = (
        db.query(OrchestrationAuditLog)
        .filter(OrchestrationAuditLog.task_id == task.id)
        .order_by(OrchestrationAuditLog.sequence_no)
        .all()
    )
    assert len(logs) == 2
    assert logs[0].sequence_no == 1
    assert logs[1].sequence_no == 2
    assert logs[0].step_type == "orchestration"
    assert logs[1].agent_name == "requirement_agent"


def test_audit_step_context_manager(db):
    task = _create_task(db)
    with audit_step(db, task.id, "verify", "verify_draft") as out:
        out["passed"] = True

    log = db.query(OrchestrationAuditLog).filter_by(task_id=task.id).first()
    assert log is not None
    assert log.status == "success"
    assert log.output_summary == {"passed": True}
    assert log.duration_ms is not None


def test_skill_executor_writes_audit_log(db):
    task = _create_task(db)
    registry = SkillRegistry()
    registry.register(CheckSensitiveWordsSkill())
    executor = SkillExecutor(registry)

    executor.execute(
        "check_sensitive_words",
        '{"text": "正常文案内容测试", "platform": "weibo"}',
        db=db,
        task_id=task.id,
        agent_name="reviewer_agent",
    )

    audit = db.query(OrchestrationAuditLog).filter_by(
        task_id=task.id, step_type="skill"
    ).first()
    assert audit is not None
    assert audit.step_name == "check_sensitive_words"
    assert audit.agent_name == "reviewer_agent"


def test_get_audit_trail_api(db):
    from app.api.v1.logs import get_audit_trail

    task = _create_task(db)
    user = db.query(User).filter_by(id=task.user_id).first()
    write_audit_log(db, task.id, "orchestration", "pipeline_start")
    write_audit_log(db, task.id, "stage", "requirement_start")

    resp = get_audit_trail(
        task_id=task.id, step_type=None, current_user=user, db=db
    )
    assert resp.success is True
    assert resp.data["total"] == 2
    assert len(resp.data["items"]) == 2
    assert resp.data["items"][0]["sequence_no"] == 1
