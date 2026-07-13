"""
Agentic 编排、任务分级、模型路由测试
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.agentic_runners import (
    handle_step_outcome,
    plan_has_more_steps,
    run_agentic_pipeline,
    run_classify_stage,
    run_plan_stage,
)
from app.utils.model_roles import get_model_for_role
from app.agents.pipeline_runners import PipelineAgents
from app.agents.pipeline_state import init_pipeline_state
from app.config import settings
from app.database import Base
from app.lang.graph.agentic_pipeline_graph import (
    build_agentic_pipeline_graph,
    run_agentic_pipeline_graph,
)
from app.models.task import Task, TaskPlatform, TaskStatus
from app.models.user import User
from app.services.planner_service import default_plan, generate_plan
from app.services.task_classifier import classify_task
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


def _create_task(db, raw_requirement: str = "写一篇 AI 就业微博") -> Task:
    user = User(
        username="agentic_user",
        email="agentic@example.com",
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


def test_classify_simple_task():
    result = classify_task("写一篇关于 AI 的微博文案", platform="weibo")
    assert result["task_mode"] == "simple"
    assert result["reasons"] == []


def test_classify_complex_task_multi_platform():
    result = classify_task(
        "请为微博和小红书分别写一篇多平台推广文案，各500字",
        platform="weibo",
    )
    assert result["task_mode"] == "complex"
    assert len(result["reasons"]) >= 1


def test_classify_complex_long_word_count():
    result = classify_task("写一篇800字的深度长文分析 AI 趋势", platform="weibo")
    assert result["task_mode"] == "complex"


def test_default_plan_has_four_steps():
    plan = default_plan("simple")
    assert len(plan["steps"]) == 4
    stages = [s["stage"] for s in plan["steps"]]
    assert stages == ["requirement", "copywriter", "verify", "reviewer"]


def test_generate_plan_simple_skips_llm():
    plan = generate_plan("短微博", "weibo", "simple")
    assert plan["source"] == "default"
    assert len(plan["steps"]) == 4


def test_model_roles_fallback_to_chat():
    assert get_model_for_role("executor") == settings.EXECUTOR_MODEL
    assert get_model_for_role("planner") == settings.PLANNER_MODEL
    assert get_model_for_role("pattern") == settings.PATTERN_MODEL


def test_verify_draft_passes_good_content():
    content = (
        "AI 正在改变就业市场，我们需要持续学习新技能，拥抱变化才能立于不败之地。"
        "无论行业如何演变，保持好奇心和执行力，才是职场人最核心的竞争力。"
    )
    state = {
        "copy_content": content,
        "parsed_requirement": {"topic": "AI", "word_count": 140},
        "raw_requirement": "AI就业",
    }
    result = verify_draft(state)
    assert result["passed"] is True


def test_verify_draft_fails_empty():
    state = {
        "copy_content": "",
        "parsed_requirement": {"topic": "AI", "word_count": 140},
    }
    result = verify_draft(state)
    assert result["passed"] is False


def test_handle_step_outcome_advances_on_success():
    state = {
        "task_id": 1,
        "current_step": 0,
        "last_step_failed": False,
        "abort": False,
    }
    updates = handle_step_outcome(state)
    assert updates["current_step"] == 1
    assert updates["retry_count"] == 0


def test_handle_step_outcome_retries_on_failure():
    state = {
        "task_id": 1,
        "current_step": 1,
        "last_step_failed": True,
        "retry_count": 0,
        "abort": False,
        "plan": {"steps": [{"step_id": "copywriter", "stage": "copywriter"}]},
    }
    updates = handle_step_outcome(state)
    assert updates["failure_level"] == "retry"
    assert updates["retry_count"] == 1


def test_plan_has_more_steps():
    state = {"plan": {"steps": [{"stage": "a"}, {"stage": "b"}]}, "current_step": 0}
    assert plan_has_more_steps(state) is True
    state["current_step"] = 2
    assert plan_has_more_steps(state) is False


def test_run_classify_and_plan_stages(db):
    task = _create_task(db, "写一篇 AI 微博")
    state, _ = init_pipeline_state(db, task.id)
    assert state is not None

    state.update(run_classify_stage(state))
    assert state["task_mode"] == "simple"

    state.update(run_plan_stage(state))
    assert len(state["plan"]["steps"]) == 4


@patch("app.agents.agentic_runners.run_full_pipeline")
def test_agentic_simple_delegates_to_fixed(mock_full, db):
    mock_full.return_value = {
        "success": True,
        "task_id": 1,
        "final_copy_id": 10,
        "review_score": 80,
        "total_tokens": 100,
        "stages": {},
    }
    task = _create_task(db)
    result = run_agentic_pipeline(db, task.id, agents=PipelineAgents())
    assert result["success"] is True
    assert result["task_mode"] == "simple"
    mock_full.assert_called_once()


def test_build_agentic_pipeline_graph():
    graph = build_agentic_pipeline_graph()
    assert graph is not None
    assert hasattr(graph, "invoke")


@patch("app.lang.graph.agentic_pipeline_graph.run_full_pipeline")
def test_agentic_graph_simple_path(mock_full, db):
    mock_full.return_value = {
        "success": True,
        "task_id": 1,
        "final_copy_id": 10,
        "review_score": 80,
        "total_tokens": 50,
        "stages": {},
    }
    task = _create_task(db, "写一篇 AI 微博")
    result = run_agentic_pipeline_graph(db, task.id)
    assert result["success"] is True
    assert result.get("task_mode") == "simple"


@patch("app.agents.agentic_runners.run_reviewer_stage")
@patch("app.agents.agentic_runners.run_copywriter_stage")
@patch("app.agents.agentic_runners.run_requirement_stage")
@patch("app.services.planner_service.get_deepseek_client")
def test_agentic_complex_pipeline(mock_client, mock_req, mock_copy, mock_review, db):
    mock_req.return_value = {
        "parsed_requirement": {"topic": "AI", "platform": "weibo", "word_count": 500},
        "hot_topics": [],
        "context_messages": [],
        "stages": {"requirement": {"success": True}},
        "total_tokens": 10,
    }
    long_content = (
        "AI 正在重塑就业市场，从制造业到服务业，几乎没有行业能置身事外。"
        "过去靠单一技能吃十年的时代结束了，复合能力与持续学习成为新常态。"
        "对普通人而言，关键不是预测哪一个岗位会消失，而是建立可迁移的学习习惯。"
        "把 AI 当作协作伙伴而非替代者，主动用它提升效率，才能在变化中占据主动。"
        "职场竞争归根到底是认知与行动力的竞争，越早开始适应，越能把握主动权。"
    )
    mock_copy.return_value = {
        "copy_id": 1,
        "copy_content": long_content,
        "stages": {"copywriter": {"success": True}},
        "total_tokens": 20,
        "abort": False,
    }
    mock_review.return_value = {
        "final_copy_id": 1,
        "review_score": 85.0,
        "stages": {"reviewer": {"success": True}},
        "total_tokens": 30,
    }

    plan_json = (
        '{"task_mode":"complex","steps":['
        '{"step_id":"requirement","stage":"requirement","description":"x","mergeable":true},'
        '{"step_id":"copywriter","stage":"copywriter","description":"x","mergeable":false},'
        '{"step_id":"verify_draft","stage":"verify","description":"x","mergeable":false},'
        '{"step_id":"reviewer","stage":"reviewer","description":"x","mergeable":false}'
        '],"reasoning":"test"}'
    )
    mock_client.return_value.chat.completions.create.return_value.choices = [
        type("Choice", (), {
            "message": type("Msg", (), {"content": plan_json})()
        })()
    ]

    task = _create_task(db, "请为微博和小红书分别写一篇500字的多平台文案")
    result = run_agentic_pipeline(db, task.id, agents=PipelineAgents())

    assert result["success"] is True
    assert result["task_mode"] == "complex"
    mock_req.assert_called()
    mock_copy.assert_called()
    mock_review.assert_called()
