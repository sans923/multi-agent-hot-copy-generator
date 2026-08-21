"""真实内容生产 P2：发布效果、偏好证据晋升与可解释洞察。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_active_user
from app.database import Base, get_db
from app.main import app
from app.models.copy import Copy
from app.models.task import Task, TaskPlatform
from app.models.user import User


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
client = TestClient(app)


def _current_user() -> User:
    return User(id=1, username="p2-owner", email="p2@example.com", hashed_password="unused", is_active=True)


def override_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def database():
    import app.models as _models  # noqa: F401

    app.dependency_overrides = {get_db: override_db, get_current_active_user: _current_user}
    Base.metadata.create_all(bind=engine)
    db = Session()
    db.add_all([
        _current_user(),
        User(id=2, username="p2-stranger", email="p2-stranger@example.com", hashed_password="unused"),
    ])
    task = Task(user_id=1, raw_requirement="企业 AI 文案", platform=TaskPlatform.TOUTIAO)
    foreign_task = Task(user_id=2, raw_requirement="其他用户", platform=TaskPlatform.TOUTIAO)
    db.add_all([task, foreign_task])
    db.flush()
    copy = Copy(task_id=task.id, title="初稿", content="支持私有化部署。", platform="toutiao", version=1)
    foreign_copy = Copy(task_id=foreign_task.id, title="他人", content="不可见", platform="toutiao", version=1)
    db.add_all([copy, foreign_copy])
    db.commit()
    ids.update(task_id=task.id, copy_id=copy.id, foreign_task_id=foreign_task.id, foreign_copy_id=foreign_copy.id)
    db.close()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


ids: dict[str, int] = {}


def test_publication_records_are_idempotent_and_metrics_can_be_backfilled():
    payload = {
        "task_id": ids["task_id"],
        "copy_id": ids["copy_id"],
        "platform": "toutiao",
        "status": "published",
        "external_id": "article-100",
        "url": "https://example.com/article-100",
        "metrics": {"impressions": 100, "clicks": 8},
        "idempotency_key": "publish-article-100",
    }
    first = client.post("/api/v1/memory/publications", json=payload)
    second = client.post("/api/v1/memory/publications", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["data"]["id"] == first.json()["data"]["id"]

    publication_id = first.json()["data"]["id"]
    updated = client.patch(
        f"/api/v1/memory/publications/{publication_id}/metrics",
        json={"metrics": {"impressions": 250, "clicks": 30, "likes": 12}},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["metrics"]["impressions"] == 250
    assert updated.json()["data"]["metrics"]["likes"] == 12

    forbidden = client.post(
        "/api/v1/memory/publications",
        json={**payload, "task_id": ids["foreign_task_id"], "copy_id": ids["foreign_copy_id"], "idempotency_key": "publish-foreign-100"},
    )
    assert forbidden.status_code == 403


def test_repeated_positive_evidence_promotes_preference_only_after_threshold():
    for index in range(2):
        response = client.post(
            "/api/v1/memory/feedback",
            json={
                "task_id": ids["task_id"],
                "copy_id": ids["copy_id"],
                "action": "accepted",
                "rating": 1,
                "comment": "采用该结尾",
                "metrics": {"style_signals": {"cta_pattern": "预约演示"}},
                "idempotency_key": f"positive-signal-{index}",
            },
        )
        assert response.status_code == 201

    before = client.get("/api/v1/memory/items?memory_type=inferred_preference")
    assert before.json()["data"] == []

    third = client.post(
        "/api/v1/memory/feedback",
        json={
            "task_id": ids["task_id"],
            "copy_id": ids["copy_id"],
            "action": "edited",
            "rating": 1,
            "comment": "保留预约 CTA",
            "edited_title": "修订稿",
            "edited_content": "支持私有化部署，预约演示了解详情。",
            "metrics": {"style_signals": {"cta_pattern": "预约演示"}},
            "idempotency_key": "positive-signal-3",
        },
    )
    assert third.status_code == 201

    after = client.get("/api/v1/memory/items?memory_type=inferred_preference")
    assert len(after.json()["data"]) == 1
    assert "预约演示" in after.json()["data"][0]["content"]

    from app.services.style_resolution_service import resolve_style_snapshot

    db = Session()
    snapshot = resolve_style_snapshot(db, user_id=1, platform="toutiao")
    assert snapshot["pattern"]["cta_pattern"] == "预约演示"
    db.close()


def test_insights_report_adoption_revision_and_publication_metrics_for_current_user_only():
    client.post(
        "/api/v1/memory/feedback",
        json={
            "task_id": ids["task_id"], "copy_id": ids["copy_id"], "action": "accepted", "rating": 1,
            "metrics": {}, "idempotency_key": "insight-accepted-1",
        },
    )
    client.post(
        "/api/v1/memory/publications",
        json={
            "task_id": ids["task_id"], "copy_id": ids["copy_id"], "platform": "toutiao",
            "status": "published", "metrics": {"impressions": 1000, "clicks": 75},
            "idempotency_key": "insight-publication-1",
        },
    )

    response = client.get("/api/v1/memory/insights")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["feedback"]["total"] == 1
    assert data["feedback"]["adoption_rate"] == 1
    assert data["publication"]["total"] == 1
    assert data["publication"]["metrics"] == {"impressions": 1000.0, "clicks": 75.0}
