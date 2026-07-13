"""
Phase 2 测试：Judge、checkpoint、人工介入恢复
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.agentic_runners import resume_agentic_pipeline, run_agentic_pipeline
from app.agents.pipeline_runners import PipelineAgents
from app.agents.pipeline_state import init_pipeline_state
from app.database import Base
from app.models.task import Task, TaskPlatform, TaskStatus
from app.models.user import User
from app.services.judge_service import judge_goal_alignment
from app.services.orchestration_persistence import (
    load_checkpoint,
    save_orchestration_meta,
    state_to_checkpoint,
)
from app.services.verify_service import verify_draft


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_database():
    from app.models import user, task, document, copy, agent_log, hotlist_sync  # noqa: F401

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


def _create_task(db, raw_requirement: str = "写一篇 AI 微博") -> Task:
    user = User(
        username="p2_user",
        email="p2@example.com",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    task = Task(
        user_id=user.id,
        raw_requirement=raw_requirement,
        platform=TaskPlatform.WEIBO,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_state_to_checkpoint_excludes_db(db):
    task = _create_task(db)
    state, _ = init_pipeline_state(db, task.id)
    assert state is not None
    state["task_mode"] = "complex"
    cp = state_to_checkpoint(state)
    assert "db" not in cp
    assert cp["task_mode"] == "complex"


def test_save_and_load_checkpoint(db):
    task = _create_task(db)
    state, _ = init_pipeline_state(db, task.id)
    assert state is not None
    state["current_step"] = 2
    state["plan"] = {"steps": [{"stage": "copywriter"}]}

    save_orchestration_meta(db, task.id, state, save_checkpoint=True)
    loaded = load_checkpoint(db, task.id)
    assert loaded is not None
    assert loaded["current_step"] == 2


@patch("app.services.verify_service.judge_goal_alignment")
def test_verify_draft_judge_fallback(mock_judge):
    mock_judge.return_value = {
        "passed": True,
        "score": 85,
        "reason": "主题相关",
        "source": "judge",
    }
    state = {
        "copy_content": (
            "这是一段关于职场发展的短文，讨论学习能力和适应变化的重要性，"
            "虽然没有直接提到指定关键词，但整体方向与成长主题相关。"
        ),
        "parsed_requirement": {"topic": "完全不相关的词", "word_count": 500},
        "raw_requirement": "AI就业",
        "platform": "weibo",
    }
    result = verify_draft(state)
    assert result["passed"] is True
    assert result["source"] == "rules+judge"
    mock_judge.assert_called_once()


@patch("app.services.judge_service.get_deepseek_client")
def test_judge_goal_alignment_parse(mock_client):
    mock_client.return_value.chat.completions.create.return_value.choices = [
        type("Choice", (), {
            "message": type("Msg", (), {
                "content": '{"passed": true, "score": 88, "reason": "满足需求"}'
            })()
        })()
    ]
    result = judge_goal_alignment("写 AI 微博", "AI 改变了世界", "weibo")
    assert result["passed"] is True
    assert result["score"] == 88


@patch("app.agents.agentic_runners._run_complex_loop")
@patch("app.agents.agentic_runners.run_classify_stage")
def test_awaiting_human_persisted(mock_classify, mock_loop, db):
    task = _create_task(db, "多平台500字文案")
    mock_classify.return_value = {
        "task_mode": "complex",
        "classify_reasons": ["多平台"],
    }
    mock_loop.return_value = {
        "db": db,
        "task_id": task.id,
        "awaiting_human": True,
        "failure_level": "human",
        "error": "需人工介入",
        "task_mode": "complex",
        "plan": {"source": "default", "steps": []},
        "stages": {},
        "total_tokens": 0,
    }

    with patch("app.agents.agentic_runners.run_plan_stage") as mock_plan:
        mock_plan.return_value = {"plan": {"steps": []}, "current_step": 0}
        result = run_agentic_pipeline(db, task.id, agents=PipelineAgents())

    assert result.get("awaiting_human") is True
    db.refresh(task)
    assert task.status == TaskStatus.AWAITING_HUMAN
    assert task.orchestration_meta is not None
    assert task.orchestration_meta.get("awaiting_human") is True


def test_resume_cancel(db):
    task = _create_task(db)
    task.status = TaskStatus.AWAITING_HUMAN
    task.orchestration_meta = {"checkpoint": {"current_step": 1}}
    db.commit()

    result = resume_agentic_pipeline(db, task.id, action="cancel")
    assert result["success"] is False
    db.refresh(task)
    assert task.status == TaskStatus.FAILED


def test_resume_accept_draft(db):
    from app.models.copy import Copy

    task = _create_task(db)
    copy = Copy(
        task_id=task.id,
        version=1,
        content="初稿内容",
        is_final=False,
        tokens_used=0,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)

    task.status = TaskStatus.AWAITING_HUMAN
    task.orchestration_meta = {"checkpoint": {"copy_id": copy.id}}
    db.commit()

    result = resume_agentic_pipeline(db, task.id, action="accept_draft")
    assert result["success"] is True
    db.refresh(task)
    assert task.status == TaskStatus.COMPLETED
