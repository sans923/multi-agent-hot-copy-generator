"""
Lead Agent 与委派 Skill 测试
==============================
不调用真实 LLM，mock 阶段 runner 或 LeadAgent._run_loop。

运行：
    pytest tests/test_lead_agent.py -v
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.lead_agent import LeadAgent
from app.agents.pipeline_context import ActivePipeline, reset_active_pipeline, set_active_pipeline
from app.agents.pipeline_runners import PipelineAgents, run_lead_pipeline
from app.agents.pipeline_state import init_pipeline_state
from app.config import settings
from app.database import Base
from app.lang.graph.lead_pipeline_graph import build_lead_pipeline_graph
from app.models.task import Task, TaskPlatform, TaskStatus
from app.models.user import User
from app.skills.delegation_skills import (
    DelegateToCopywriterSkill,
    DelegateToRequirementSkill,
    DelegateToReviewerSkill,
    FinishTaskSkill,
)


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


def _create_task(db, raw_requirement: str = "写一篇 AI 就业微博") -> Task:
    user = User(
        username="lead_user",
        email="lead@example.com",
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


def _mock_stage_returns():
    return {
        "requirement": {
            "parsed_requirement": {"topic": "AI就业", "platform": "weibo"},
            "hot_topics": [],
            "context_messages": [],
            "stages": {"requirement": {"success": True, "tokens_used": 10}},
            "total_tokens": 10,
        },
        "copywriter": {
            "copy_id": 201,
            "copy_content": "mock",
            "stages": {
                "requirement": {"success": True, "tokens_used": 10},
                "copywriter": {"success": True, "copy_id": 201, "tokens_used": 20},
            },
            "total_tokens": 30,
            "abort": False,
        },
        "reviewer": {
            "final_copy_id": 201,
            "review_score": 88.0,
            "stages": {
                "requirement": {"success": True, "tokens_used": 10},
                "copywriter": {"success": True, "copy_id": 201, "tokens_used": 20},
                "reviewer": {"success": True, "review_score": 88.0, "tokens_used": 12},
            },
            "total_tokens": 42,
        },
    }


@patch("app.agents.lead_agent.LeadAgent._run_loop")
def test_lead_agent_finish_via_finish_task(mock_loop, db):
    mocks = _mock_stage_returns()
    task = _create_task(db)

    mock_loop.return_value = {
        "success": True,
        "tokens_used": 50,
        "tool_results": [
            {
                "skill_name": "finish_task",
                "result": {
                    "success": True,
                    "finished": True,
                    "task_id": task.id,
                    "final_copy_id": 201,
                    "review_score": 88.0,
                    "total_tokens": 42,
                    "stages": mocks["reviewer"]["stages"],
                    "orchestration_mode": "lead",
                },
            }
        ],
    }

    agent = LeadAgent()
    result = agent.run(db=db, task_id=task.id)

    assert result["success"] is True
    assert result.get("orchestration_mode") == "lead"
    assert result["final_copy_id"] == 201


@patch("app.agents.pipeline_runners.run_reviewer_stage")
@patch("app.agents.pipeline_runners.run_copywriter_stage")
@patch("app.agents.pipeline_runners.run_requirement_stage")
def test_delegation_skills_full_flow(mock_req, mock_copy, mock_review, db):
    mocks = _mock_stage_returns()
    mock_req.return_value = mocks["requirement"]
    mock_copy.return_value = mocks["copywriter"]
    mock_review.return_value = mocks["reviewer"]

    task = _create_task(db)
    state, _ = init_pipeline_state(db, task.id)
    assert state is not None

    active = ActivePipeline(state=state, agents=PipelineAgents())
    token = set_active_pipeline(active)

    try:
        req_skill = DelegateToRequirementSkill()
        copy_skill = DelegateToCopywriterSkill()
        review_skill = DelegateToReviewerSkill()
        finish_skill = FinishTaskSkill()

        r1 = req_skill.execute(db=db)
        assert r1["success"] is True
        assert r1["delegated_to"] == "requirement_agent"

        r2 = copy_skill.execute(db=db)
        assert r2["success"] is True
        assert active.state["copy_id"] == 201

        r3 = review_skill.execute(db=db)
        assert r3["success"] is True
        assert active.state["review_score"] == 88.0

        r4 = finish_skill.execute(db=db)
        assert r4["success"] is True
        assert r4["finished"] is True
        assert active.state["stages"]["requirement"]["delegated_by"] == "lead_agent"
    finally:
        reset_active_pipeline(token)


@patch("app.agents.lead_agent.LeadAgent.run")
def test_run_lead_pipeline_delegates(mock_run, db):
    mock_run.return_value = {"success": True, "task_id": 1}
    task = _create_task(db)
    result = run_lead_pipeline(db, task.id)
    assert result["success"] is True
    mock_run.assert_called_once()


def test_build_lead_pipeline_graph():
    graph = build_lead_pipeline_graph()
    assert graph is not None
    assert hasattr(graph, "invoke")


@patch("app.lang.graph.lead_pipeline_graph.run_lead_pipeline")
def test_lead_pipeline_graph_success(mock_run_lead, db):
    task = _create_task(db)
    mock_run_lead.return_value = {
        "success": True,
        "task_id": task.id,
        "final_copy_id": 201,
        "orchestration_mode": "lead",
    }

    from app.lang.graph.lead_pipeline_graph import run_lead_pipeline_graph

    result = run_lead_pipeline_graph(db, task.id)
    assert result["success"] is True
    assert result.get("orchestration_mode") == "lead"


@patch("app.agents.pipeline_runners.run_lead_pipeline")
@patch("app.agents.pipeline_runners.run_full_pipeline")
def test_orchestrator_lead_mode(mock_fixed, mock_lead, db, monkeypatch):
    monkeypatch.setattr(settings, "ORCHESTRATION_MODE", "lead")
    mock_lead.return_value = {"success": True, "task_id": 1, "orchestration_mode": "lead"}

    from app.agents.orchestrator import AgentOrchestrator

    task = _create_task(db)
    result = AgentOrchestrator().run(db=db, task_id=task.id)

    mock_lead.assert_called_once()
    mock_fixed.assert_not_called()
    assert result["orchestration_mode"] == "lead"
