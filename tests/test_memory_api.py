"""长期记忆 API、索引调度和风格卡生产链集成。"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_active_user
from app.database import Base, get_db
from app.main import app
from app.models.copy import Copy
from app.models.memory import MemoryFeedback, MemoryItem, StyleCardVersion, UserPreference
from app.models.memory_index_job import MemoryIndexJob
from app.models.task import Task, TaskPlatform
from app.models.toutiao_reference import ToutiaoReference
from app.models.user import User
from app.services.content_asset_service import build_style_card
from app.services.memory_index_service import (
    enqueue_copy_index,
    process_pending_memory_index_jobs,
)
from app.services.memory_service import record_copy_feedback


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
client = TestClient(app)


def override_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _current_user() -> User:
    return User(
        id=1,
        username="memory-api",
        email="memory-api@example.com",
        hashed_password="unused",
        is_active=True,
    )


@pytest.fixture(autouse=True)
def database():
    import app.models as _models  # noqa: F401

    app.dependency_overrides = {
        get_db: override_db,
        get_current_active_user: _current_user,
    }
    Base.metadata.create_all(bind=engine)
    db = Session()
    db.add(_current_user())
    db.commit()
    db.close()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _owned_task_and_copy() -> tuple[int, int, str]:
    db = Session()
    task = Task(
        user_id=1,
        raw_requirement="记忆 API 测试任务",
        platform=TaskPlatform.WEIBO,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    copy = Copy(
        task_id=task.id,
        content="可提交反馈的文案",
        platform="weibo",
        is_final=True,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    result = (task.id, copy.id, copy.content)
    db.close()
    return result


def test_preferences_api_supports_get_patch_and_optimistic_version():
    empty = client.get("/api/v1/memory/preferences")
    assert empty.status_code == 200
    assert empty.json()["data"]["version"] == 0

    updated = client.put(
        "/api/v1/memory/preferences",
        json={
            "preferences": {"brand_voice": "专业简洁", "banned_terms": ["震惊"]},
            "expected_version": 0,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["version"] == 1

    conflict = client.put(
        "/api/v1/memory/preferences",
        json={"preferences": {"brand_voice": "幽默"}, "expected_version": 0},
    )
    assert conflict.status_code == 409


def test_feedback_api_is_idempotent_and_owned():
    task_id, copy_id, _ = _owned_task_and_copy()
    payload = {
        "task_id": task_id,
        "copy_id": copy_id,
        "action": "accepted",
        "rating": 1,
        "comment": "标题保留",
        "metrics": {"clicks": 3},
        "idempotency_key": "api-feedback-1",
    }
    first = client.post("/api/v1/memory/feedback", json=payload)
    repeated = client.post("/api/v1/memory/feedback", json=payload)

    assert first.status_code == 201
    assert repeated.status_code == 201
    assert first.json()["data"]["id"] == repeated.json()["data"]["id"]


def test_memory_items_api_never_returns_other_users_items():
    db = Session()
    stranger = User(
        id=2,
        username="memory-api-stranger",
        email="memory-api-stranger@example.com",
        hashed_password="unused",
    )
    db.add(stranger)
    db.add_all([
        MemoryItem(
            user_id=1,
            memory_type="brand_rule",
            scope_id="default",
            source_type="explicit_preference",
            source_id="own",
            content="自己的记忆",
            content_hash="api-own",
            status="active",
        ),
        MemoryItem(
            user_id=2,
            memory_type="brand_rule",
            scope_id="default",
            source_type="explicit_preference",
            source_id="foreign",
            content="别人的记忆",
            content_hash="api-foreign",
            status="active",
        ),
    ])
    db.commit()
    db.close()

    response = client.get("/api/v1/memory/items")

    assert response.status_code == 200
    items = response.json()["data"]
    assert [item["content"] for item in items] == ["自己的记忆"]


def test_index_scheduler_processes_outbox_without_model_side_effects():
    task_id, copy_id, copy_content = _owned_task_and_copy()
    db = Session()
    enqueue_copy_index(
        db,
        copy_id=copy_id,
        user_id=1,
        payload={
            "copy_id": copy_id,
            "task_id": task_id,
            "content": copy_content,
            "platform": "weibo",
        },
    )
    db.close()

    from app.scheduler import job_index_copy_memory

    with patch("app.services.embedding_service.upsert_copy_to_chroma") as upsert:
        job_index_copy_memory(session_factory=Session)

    db = Session()
    row = db.query(MemoryIndexJob).one()
    assert row.status == "completed"
    assert row.attempts == 1
    db.close()
    upsert.assert_called_once()


def test_index_worker_claims_job_before_external_vector_write():
    task_id, copy_id, copy_content = _owned_task_and_copy()
    db = Session()
    enqueue_copy_index(
        db,
        copy_id=copy_id,
        user_id=1,
        payload={
            "copy_id": copy_id,
            "task_id": task_id,
            "content": copy_content,
            "platform": "weibo",
        },
    )
    db.close()

    calls = 0

    def competing_upsert(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            competitor = Session()
            process_pending_memory_index_jobs(competitor)
            competitor.close()

    worker = Session()
    with patch(
        "app.services.embedding_service.upsert_copy_to_chroma",
        side_effect=competing_upsert,
    ):
        process_pending_memory_index_jobs(worker)
    worker.close()

    assert calls == 1


def test_feedback_idempotency_key_is_scoped_to_user():
    task_id, copy_id, _ = _owned_task_and_copy()
    db = Session()
    stranger = User(
        id=2,
        username="memory-feedback-stranger",
        email="memory-feedback-stranger@example.com",
        hashed_password="unused",
    )
    db.add(stranger)
    stranger_task = Task(
        user_id=2,
        raw_requirement="另一个用户的反馈任务",
        platform=TaskPlatform.WEIBO,
    )
    db.add(stranger_task)
    db.commit()
    db.refresh(stranger_task)
    stranger_copy = Copy(
        task_id=stranger_task.id,
        content="另一个用户的文案",
        platform="weibo",
        is_final=True,
    )
    db.add(stranger_copy)
    db.commit()
    db.refresh(stranger_copy)

    for user_id, owned_task_id, owned_copy_id in (
        (1, task_id, copy_id),
        (2, stranger_task.id, stranger_copy.id),
    ):
        record_copy_feedback(
            db,
            user_id=user_id,
            task_id=owned_task_id,
            copy_id=owned_copy_id,
            action="accepted",
            rating=1,
            idempotency_key="shared-request-key",
        )

    assert db.query(MemoryFeedback).count() == 2
    db.close()


def test_content_asset_build_creates_active_style_card_version(monkeypatch):
    db = Session()
    reference = ToutiaoReference(
        article_id="versioned-reference",
        title="版本化参考文章",
        content="参考正文" * 100,
        keyword="AI就业",
        like_count=100,
    )
    db.add(reference)
    db.commit()
    db.refresh(reference)
    monkeypatch.setattr(
        "app.services.content_asset_service.extract_writing_pattern_from_articles",
        lambda articles, platform: {
            "success": True,
            "writing_pattern": {"hook": {"type": "反常识"}, "confidence": 0.8},
        },
    )

    card = build_style_card(db, topic_cluster="AI就业", reference_ids=[reference.id])

    version = db.query(StyleCardVersion).filter_by(style_card_id=card.id).one()
    assert version.status == "active"
    assert version.pattern_json == card.pattern_json
    db.close()
