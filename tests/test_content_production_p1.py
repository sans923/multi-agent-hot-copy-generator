"""真实内容生产 P1：Brief、知识治理、混合检索和分层风格。"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_active_user
from app.database import Base, get_db
from app.main import app
from app.models.memory import StyleCardVersion, UserPreference
from app.models.style_card import StyleCard
from app.models.task import Task, TaskPlatform
from app.models.user import User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
client = TestClient(app)


def _current_user() -> User:
    return User(
        id=1,
        username="p1-owner",
        email="p1-owner@example.com",
        hashed_password="unused",
        is_active=True,
    )


def override_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def database():
    import app.models as _models  # noqa: F401

    app.dependency_overrides = {
        get_db: override_db,
        get_current_active_user: _current_user,
    }
    Base.metadata.create_all(bind=engine)
    db = Session()
    db.add_all([
        _current_user(),
        User(
            id=2,
            username="p1-stranger",
            email="p1-stranger@example.com",
            hashed_password="unused",
            is_active=True,
        ),
    ])
    db.commit()
    db.close()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _owned_task() -> int:
    db = Session()
    task = Task(
        user_id=1,
        raw_requirement="为企业 AI 产品写一篇专业长文",
        platform=TaskPlatform.TOUTIAO,
    )
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()
    return task_id


def test_content_brief_reports_missing_fields_before_becoming_ready():
    task_id = _owned_task()

    incomplete = client.put(
        f"/api/v1/tasks/{task_id}/brief",
        json={"topic": "企业 AI", "audience": "技术负责人"},
    )

    assert incomplete.status_code == 200
    assert incomplete.json()["data"]["completeness_score"] < 1
    assert set(incomplete.json()["data"]["missing_fields"]) == {"goal", "key_points"}

    complete = client.put(
        f"/api/v1/tasks/{task_id}/brief",
        json={
            "topic": "企业 AI",
            "audience": "技术负责人",
            "goal": "预约产品演示",
            "key_points": ["私有化部署", "审计能力"],
        },
    )

    assert complete.status_code == 200
    assert complete.json()["data"]["completeness_score"] == 1
    db = Session()
    task = db.query(Task).filter(Task.id == task_id).one()
    assert task.content_status == "brief_ready"
    assert task.content_brief["goal"] == "预约产品演示"
    db.close()


def test_knowledge_sources_are_versioned_owned_and_searchable_with_citations():
    own = client.post(
        "/api/v1/knowledge/sources",
        json={
            "knowledge_type": "product_fact",
            "title": "企业 AI 产品说明",
            "content": "支持私有化部署，并提供完整审计日志。",
            "source_uri": "internal://product/enterprise-ai",
            "metadata": {"quality_score": 0.9},
        },
    )
    assert own.status_code == 201
    own_id = own.json()["data"]["id"]

    db = Session()
    from app.models.knowledge import KnowledgeSource

    db.add_all([
        KnowledgeSource(
            user_id=2,
            knowledge_type="product_fact",
            title="其他用户私有资料",
            content="其他用户也支持私有化部署。",
            content_hash="foreign-source",
            status="active",
            version=1,
        ),
        KnowledgeSource(
            user_id=1,
            knowledge_type="product_fact",
            title="过期资料",
            content="已经失效的私有化部署承诺。",
            content_hash="expired-source",
            status="active",
            version=1,
            valid_to=datetime.utcnow() - timedelta(days=1),
        ),
    ])
    db.commit()
    db.close()

    response = client.post(
        "/api/v1/knowledge/search",
        json={"query": "私有化部署 审计", "knowledge_types": ["product_fact"]},
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["source_id"] for item in items] == [own_id]
    assert items[0]["citation"]["source_uri"] == "internal://product/enterprise-ai"
    assert items[0]["score"] > 0


def test_hybrid_ranking_deduplicates_and_combines_lexical_and_vector_scores():
    from app.services.knowledge_service import merge_hybrid_results

    merged = merge_hybrid_results(
        lexical=[
            {"chunk_id": 1, "lexical_score": 0.9},
            {"chunk_id": 2, "lexical_score": 0.8},
        ],
        vector=[
            {"chunk_id": 2, "vector_score": 0.95},
            {"chunk_id": 3, "vector_score": 0.7},
        ],
        lexical_weight=0.4,
        vector_weight=0.6,
    )

    assert [item["chunk_id"] for item in merged] == [2, 1, 3]
    assert len({item["chunk_id"] for item in merged}) == 3
    assert merged[0]["score"] == pytest.approx(0.89)


def test_style_resolution_merges_platform_brand_selected_and_task_layers():
    from app.services.style_resolution_service import resolve_style_snapshot

    db = Session()
    platform_card = StyleCard(
        topic_cluster="__platform_default__",
        platform="toutiao",
        pattern_json={"rhythm": {"sentence_style": "短句"}, "banned_terms": ["最强"]},
        layer="platform",
        priority=10,
        status="active",
    )
    selected_card = StyleCard(
        topic_cluster="企业 AI",
        platform="toutiao",
        pattern_json={"hook": {"type": "数据式"}, "banned_terms": ["震惊"]},
        owner_id=1,
        layer="account",
        priority=30,
        status="active",
    )
    db.add_all([platform_card, selected_card])
    db.commit()
    db.refresh(selected_card)
    db.add(StyleCardVersion(
        style_card_id=selected_card.id,
        version=3,
        pattern_json={"hook": {"type": "反常识"}, "banned_terms": ["震惊"]},
        status="active",
        source_article_ids=["style-source"],
    ))
    db.add(UserPreference(
        user_id=1,
        preferences={"brand_voice": "专业克制", "banned_terms": ["保证"]},
        version=1,
    ))
    db.commit()

    snapshot = resolve_style_snapshot(
        db,
        user_id=1,
        platform="toutiao",
        selected_style_card_id=selected_card.id,
        task_override={"hook": {"type": "疑问式"}, "cta_pattern": "预约演示"},
    )

    assert snapshot["pattern"]["rhythm"]["sentence_style"] == "短句"
    assert snapshot["pattern"]["brand_voice"] == "专业克制"
    assert snapshot["pattern"]["hook"]["type"] == "疑问式"
    assert snapshot["pattern"]["cta_pattern"] == "预约演示"
    assert snapshot["pattern"]["banned_terms"] == ["最强", "保证", "震惊"]
    assert snapshot["selected_style_version"] == 3
    assert [layer["layer"] for layer in snapshot["layers"]] == [
        "platform", "brand", "account", "task"
    ]
    db.close()
