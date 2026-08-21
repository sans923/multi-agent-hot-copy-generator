"""长期记忆生命周期：偏好、反馈、版本、预算和检索装配。"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.pipeline_state import PipelineState
from app.database import Base
from app.models.copy import Copy
from app.models.memory import MemoryFeedback, MemoryItem, StyleCardVersion, UserPreference
from app.models.style_card import StyleCard
from app.models.task import Task, TaskPlatform
from app.models.user import User
from app.services.memory_service import (
    activate_memory_version,
    assemble_memory_context,
    record_copy_feedback,
    save_style_card_version,
    upsert_user_preferences,
)
from app.services.orchestration_persistence import checkpoint_to_state, state_to_checkpoint
from app.skills.rag_skills import SearchSimilarCopiesSkill


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _user(db, suffix: str) -> User:
    user = User(
        username=f"lifecycle-{suffix}",
        email=f"lifecycle-{suffix}@example.com",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _task_and_copy(db, user: User, title: str = "memory-copy") -> tuple[Task, Copy]:
    task = Task(
        user_id=user.id,
        raw_requirement="写一篇用于记忆反馈测试的文章",
        platform=TaskPlatform.WEIBO,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    copy = Copy(
        task_id=task.id,
        title=title,
        content="人工智能产品设计与工程实践",
        platform="weibo",
        review_score=88,
        is_final=True,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return task, copy


def test_user_preferences_patch_is_versioned_and_user_scoped(db):
    owner = _user(db, "preference-owner")
    stranger = _user(db, "preference-stranger")

    first = upsert_user_preferences(
        db,
        user_id=owner.id,
        patch={"brand_voice": "专业克制", "banned_terms": ["震惊"]},
    )
    second = upsert_user_preferences(
        db,
        user_id=owner.id,
        patch={"target_audience": "Python 工程师"},
        expected_version=first.version,
    )

    assert second.version == 2
    assert second.preferences == {
        "brand_voice": "专业克制",
        "banned_terms": ["震惊"],
        "target_audience": "Python 工程师",
    }
    assert db.query(UserPreference).filter_by(user_id=stranger.id).count() == 0


def test_user_preferences_reject_stale_version(db):
    owner = _user(db, "preference-conflict")
    upsert_user_preferences(db, user_id=owner.id, patch={"brand_voice": "理性"})

    with pytest.raises(ValueError, match="版本冲突"):
        upsert_user_preferences(
            db,
            user_id=owner.id,
            patch={"brand_voice": "幽默"},
            expected_version=0,
        )


def test_feedback_validates_copy_ownership_and_is_idempotent(db):
    owner = _user(db, "feedback-owner")
    stranger = _user(db, "feedback-stranger")
    task, copy = _task_and_copy(db, owner)

    feedback = record_copy_feedback(
        db,
        user_id=owner.id,
        task_id=task.id,
        copy_id=copy.id,
        action="accepted",
        rating=1,
        comment="保留标题，正文更专业",
        metrics={"clicks": 12},
        idempotency_key="feedback-1",
    )
    repeated = record_copy_feedback(
        db,
        user_id=owner.id,
        task_id=task.id,
        copy_id=copy.id,
        action="accepted",
        rating=1,
        idempotency_key="feedback-1",
    )

    assert repeated.id == feedback.id
    assert db.query(MemoryFeedback).count() == 1
    with pytest.raises(ValueError, match="无权"):
        record_copy_feedback(
            db,
            user_id=stranger.id,
            task_id=task.id,
            copy_id=copy.id,
            action="accepted",
            rating=1,
            idempotency_key="feedback-foreign",
        )


def test_memory_activation_supersedes_previous_version(db):
    owner = _user(db, "memory-version")
    first = MemoryItem(
        user_id=owner.id,
        memory_type="brand_rule",
        scope_id="default",
        source_type="explicit_preference",
        source_id="voice",
        content="语气专业",
        content_hash="hash-1",
        version=1,
        status="candidate",
    )
    second = MemoryItem(
        user_id=owner.id,
        memory_type="brand_rule",
        scope_id="default",
        source_type="explicit_preference",
        source_id="voice",
        content="语气专业且简洁",
        content_hash="hash-2",
        version=2,
        status="candidate",
    )
    db.add_all([first, second])
    db.commit()

    activate_memory_version(db, second.id)
    db.refresh(first)
    db.refresh(second)

    assert first.status == "superseded"
    assert second.status == "active"
    assert second.supersedes_id == first.id


def test_style_card_versions_are_append_only(db):
    card = StyleCard(
        topic_cluster="AI就业",
        platform="toutiao",
        pattern_json={"hook": {"type": "疑问式"}},
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    v1 = save_style_card_version(
        db,
        style_card=card,
        pattern={"hook": {"type": "疑问式"}},
        status="active",
        source_article_ids=["a1"],
    )
    v2 = save_style_card_version(
        db,
        style_card=card,
        pattern={"hook": {"type": "反常识"}},
        status="active",
        source_article_ids=["a1", "a2"],
    )

    db.refresh(v1)
    assert (v1.version, v1.status) == (1, "superseded")
    assert (v2.version, v2.status, v2.supersedes_id) == (2, "active", v1.id)
    assert db.query(StyleCardVersion).filter_by(style_card_id=card.id).count() == 2
    assert card.pattern_json == {"hook": {"type": "反常识"}}


def test_context_assembly_filters_expired_and_respects_budget(db):
    owner = _user(db, "context")
    active = MemoryItem(
        user_id=owner.id,
        memory_type="brand_rule",
        scope_id="default",
        source_type="explicit_preference",
        source_id="active",
        content="A" * 500,
        content_hash="context-active",
        version=1,
        status="active",
        quality_score=0.9,
    )
    expired = MemoryItem(
        user_id=owner.id,
        memory_type="brand_rule",
        scope_id="default",
        source_type="explicit_preference",
        source_id="expired",
        content="不应出现",
        content_hash="context-expired",
        version=1,
        status="active",
        expires_at=datetime.utcnow() - timedelta(seconds=1),
    )
    db.add_all([active, expired])
    db.commit()

    assembled = assemble_memory_context(db, user_id=owner.id, max_chars=120, max_items=5)

    assert assembled["total_chars"] <= 120
    assert len(assembled["items"]) == 1
    assert assembled["items"][0]["memory_id"] == active.id
    assert "不应出现" not in assembled["text"]


def test_hybrid_retrieval_deduplicates_filters_and_budgets(db):
    owner = _user(db, "hybrid")
    task, copy = _task_and_copy(db, owner, title="db-copy")
    skill = SearchSimilarCopiesSkill()
    vector_results = [
        {
            "copy_id": copy.id,
            "content": "人工智能产品设计与工程实践",
            "title": "vector-copy",
            "platform": "weibo",
            "review_score": 88,
            "similarity": 0.91,
        },
        {
            "copy_id": 999,
            "content": "低相关内容",
            "title": "low-score",
            "platform": "weibo",
            "review_score": 90,
            "similarity": 0.1,
        },
    ]
    with patch.object(skill, "_search_from_chromadb", return_value=vector_results):
        result = skill.execute(
            db,
            query_text="人工智能 产品 工程",
            platform="weibo",
            task_id=task.id,
            limit=5,
            max_context_chars=80,
            similarity_threshold=0.35,
        )

    assert result["retrieval_source"] == "hybrid"
    assert len(result["similar_copies"]) == 1
    assert result["similar_copies"][0]["copy_id"] == copy.id
    assert sum(len(item["content"]) for item in result["similar_copies"]) <= 80


def test_checkpoint_has_schema_version_and_prunes_unbounded_messages(db):
    state: PipelineState = {
        "task_id": 42,
        "context_messages": [
            {"role": "assistant", "content": str(index) + "X" * 5000}
            for index in range(100)
        ],
        "decision_log": [{"step": index} for index in range(100)],
        "reflect_notes": ["R" * 5000 for _ in range(100)],
    }

    checkpoint = state_to_checkpoint(state)

    assert checkpoint["_schema_version"] == 2
    assert len(checkpoint["context_messages"]) <= 20
    assert all(len(item["content"]) <= 2000 for item in checkpoint["context_messages"])
    assert len(checkpoint["decision_log"]) <= 50
    assert len(checkpoint["reflect_notes"]) <= 20

    restored = checkpoint_to_state(checkpoint, db, 42)
    assert restored["task_id"] == 42
    assert "_schema_version" not in restored


def test_checkpoint_rejects_unknown_future_schema(db):
    with pytest.raises(ValueError, match="版本"):
        checkpoint_to_state({"_schema_version": 999}, db, 1)
