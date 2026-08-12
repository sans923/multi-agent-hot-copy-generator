"""
编排引擎与 LangGraph 主流程图测试
==================================
不调用真实 LLM，通过 mock 阶段执行器验证双引擎行为一致。

运行：
    pytest tests/test_orchestration.py -v
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.pipeline_runners import PipelineAgents, run_full_pipeline
from app.agents.pipeline_state import init_pipeline_state
from app.database import Base
from app.lang.graph.copy_pipeline_graph import build_copy_pipeline_graph, run_copy_pipeline
from app.models.task import Task, TaskPlatform, TaskStatus
from app.models.user import User
from app.orchestration import get_orchestration_engine
from app.orchestration.langgraph_engine import LangGraphOrchestrationEngine
from app.orchestration.native_engine import NativeOrchestrationEngine
from app.services.langgraph_checkpoint import ParameterizedSqliteSaver


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
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
        username="orch_user",
        email="orch@example.com",
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
    """模拟三阶段全部成功的返回值。"""
    return {
        "requirement": {
            "parsed_requirement": {"topic": "AI就业", "platform": "weibo", "style": "口语化"},
            "hot_topics": [{"title": "AI热点"}],
            "context_messages": [],
            "stages": {"requirement": {"success": True, "tokens_used": 10}},
            "total_tokens": 10,
        },
        "copywriter": {
            "copy_id": 101,
            "copy_content": "mock copy content",
            "stages": {
                "requirement": {"success": True, "tokens_used": 10},
                "copywriter": {"success": True, "copy_id": 101, "tokens_used": 20},
            },
            "total_tokens": 30,
            "abort": False,
        },
        "reviewer": {
            "final_copy_id": 101,
            "review_score": 85.0,
            "stages": {
                "requirement": {"success": True, "tokens_used": 10},
                "copywriter": {"success": True, "copy_id": 101, "tokens_used": 20},
                "reviewer": {"success": True, "review_score": 85.0, "tokens_used": 15},
            },
            "total_tokens": 45,
        },
    }


def test_factory_registers_langgraph_engine():
    engine = get_orchestration_engine("langgraph")
    assert isinstance(engine, LangGraphOrchestrationEngine)
    assert engine.name == "langgraph"


def test_factory_native_engine():
    engine = get_orchestration_engine("native")
    assert isinstance(engine, NativeOrchestrationEngine)
    assert engine.name == "native"


def test_build_copy_pipeline_graph():
    graph = build_copy_pipeline_graph()
    assert graph is not None
    assert hasattr(graph, "invoke")


def test_init_pipeline_state_missing_task(db):
    state, error = init_pipeline_state(db, task_id=9999)
    assert state is None
    assert error is not None
    assert error["success"] is False


def test_init_pipeline_state_success(db):
    task = _create_task(db)
    state, error = init_pipeline_state(db, task.id)
    assert error is None
    assert state is not None
    assert state["task_id"] == task.id
    assert state["raw_requirement"] == task.raw_requirement
    assert state["platform"] == "weibo"


@patch("app.agents.pipeline_runners.run_reviewer_stage")
@patch("app.agents.pipeline_runners.run_copywriter_stage")
@patch("app.agents.pipeline_runners.run_requirement_stage")
def test_run_full_pipeline_success(mock_req, mock_copy, mock_review, db):
    mocks = _mock_stage_returns()
    mock_req.return_value = mocks["requirement"]
    mock_copy.return_value = mocks["copywriter"]
    mock_review.return_value = mocks["reviewer"]

    task = _create_task(db)
    result = run_full_pipeline(db, task.id, agents=PipelineAgents())

    assert result["success"] is True
    assert result["task_id"] == task.id
    assert result["final_copy_id"] == 101
    assert result["review_score"] == 85.0
    assert result["total_tokens"] == 45
    assert "requirement" in result["stages"]
    assert "copywriter" in result["stages"]
    assert "reviewer" in result["stages"]


@patch("app.lang.graph.copy_pipeline_graph.run_requirement_stage")
@patch("app.lang.graph.copy_pipeline_graph.run_copywriter_stage")
@patch("app.lang.graph.copy_pipeline_graph.run_reviewer_stage")
def test_run_copy_pipeline_success(mock_review, mock_copy, mock_req, db):
    mocks = _mock_stage_returns()
    mock_req.return_value = mocks["requirement"]
    mock_copy.return_value = mocks["copywriter"]
    mock_review.return_value = mocks["reviewer"]

    task = _create_task(db)
    result = run_copy_pipeline(db, task.id)

    assert result["success"] is True
    assert result["final_copy_id"] == 101
    assert result["review_score"] == 85.0


@patch("app.agents.pipeline_runners.run_copywriter_stage")
@patch("app.agents.pipeline_runners.run_requirement_stage")
def test_run_full_pipeline_copywriter_failure(mock_req, mock_copy, db):
    mocks = _mock_stage_returns()
    mock_req.return_value = mocks["requirement"]
    mock_copy.return_value = {
        "stages": {
            "requirement": {"success": True, "tokens_used": 10},
            "copywriter": {"success": False, "tokens_used": 5},
        },
        "total_tokens": 15,
        "abort": True,
        "error": "文案创作失败",
    }

    task = _create_task(db)
    result = run_full_pipeline(db, task.id, agents=PipelineAgents())

    assert result["success"] is False
    assert result["error"] == "文案创作失败"
    assert "copywriter" in result["stages"]


@patch("app.lang.graph.copy_pipeline_graph.run_copywriter_stage")
@patch("app.lang.graph.copy_pipeline_graph.run_requirement_stage")
def test_run_copy_pipeline_copywriter_failure(mock_req, mock_copy, db):
    mocks = _mock_stage_returns()
    mock_req.return_value = mocks["requirement"]
    mock_copy.return_value = {
        "stages": {
            "requirement": {"success": True, "tokens_used": 10},
            "copywriter": {"success": False, "tokens_used": 5},
        },
        "total_tokens": 15,
        "abort": True,
        "error": "mock copywriter error",
    }

    task = _create_task(db)
    result = run_copy_pipeline(db, task.id)

    assert result["success"] is False
    assert result["error"] == "mock copywriter error"


@patch("app.agents.orchestrator.AgentOrchestrator")
def test_native_engine_delegates_to_orchestrator(mock_orchestrator_cls, db):
    mock_instance = mock_orchestrator_cls.return_value
    mock_instance.run.return_value = {"success": True, "task_id": 1}

    engine = NativeOrchestrationEngine()
    result = engine.run(db=db, task_id=1)

    mock_orchestrator_cls.assert_called_once()
    mock_instance.run.assert_called_once_with(db=db, task_id=1)
    assert result["success"] is True


@patch("app.lang.graph.copy_pipeline_graph.run_copy_pipeline")
def test_langgraph_engine_delegates_to_graph(mock_run_copy_pipeline, db):
    mock_run_copy_pipeline.return_value = {"success": True, "task_id": 2}

    engine = LangGraphOrchestrationEngine()
    result = engine.run(db=db, task_id=2)

    mock_run_copy_pipeline.assert_called_once_with(db=db, task_id=2)
    assert result["success"] is True


@patch("app.lang.graph.agentic_pipeline_graph.decide_final_quality_gate")
@patch("app.lang.graph.agentic_pipeline_graph.run_execute_current_step")
@patch("app.lang.graph.agentic_pipeline_graph.run_plan_stage")
@patch("app.lang.graph.agentic_pipeline_graph.run_classify_stage")
def test_langgraph_engine_resumes_interrupted_task_after_rebuild(
    mock_classify,
    mock_plan,
    mock_execute,
    mock_quality_gate,
    db,
    tmp_path,
):
    mock_classify.return_value = {"task_mode": "complex", "classify_reasons": []}
    mock_plan.return_value = {
        "plan": {
            "source": "default",
            "steps": [{"step_id": "reviewer", "stage": "reviewer"}],
        },
        "current_step": 0,
    }
    mock_execute.side_effect = [
        {
            "awaiting_human": True,
            "failure_level": "human",
            "error": "需要人工确认",
            "last_step_failed": False,
        },
        {
            "final_copy_id": 10,
            "review_score": 90.0,
            "total_tokens": 5,
            "stages": {"reviewer": {"success": True}},
            "last_step_failed": False,
            "step_count": 1,
        },
    ]
    mock_quality_gate.return_value = type("Decision", (), {
        "passed": True,
        "action": "finalize",
        "failed_checks": [],
        "as_dict": lambda self: {
            "passed": True,
            "action": "finalize",
            "failed_checks": [],
        },
    })()
    task = _create_task(db, "复杂任务需要人工确认")
    task.orchestration_meta = {
        "execution_mode": "plan",
        "resolved_mode": "agentic",
    }
    db.commit()
    checkpoint_path = tmp_path / "agentic-checkpoints.sqlite3"

    first_engine = LangGraphOrchestrationEngine(
        checkpointer=ParameterizedSqliteSaver(checkpoint_path),
        session_factory=TestSessionLocal,
    )
    paused = first_engine.start(db, task.id)
    db.refresh(task)
    thread_id = task.orchestration_meta["thread_id"]
    first_engine.close()

    assert paused["awaiting_human"] is True
    assert task.status == TaskStatus.AWAITING_HUMAN
    assert "checkpoint" not in task.orchestration_meta

    rebuilt_engine = LangGraphOrchestrationEngine(
        checkpointer=ParameterizedSqliteSaver(checkpoint_path),
        session_factory=TestSessionLocal,
    )
    snapshot = rebuilt_engine.get_state(thread_id=thread_id)
    resumed = rebuilt_engine.resume(
        db,
        task.id,
        thread_id=thread_id,
        human_input={"action": "retry"},
    )
    rebuilt_engine.close()

    assert snapshot["interrupts"][0]["allowed_actions"] == [
        "retry", "accept_draft", "cancel",
    ]
    assert resumed["success"] is True
    db.refresh(task)
    assert task.status == TaskStatus.COMPLETED
