"""真实内容生产 P0：三域状态、生成快照和用户反馈版本。"""

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_active_user
from app.database import Base, get_db
from app.main import app
from app.models.copy import Copy
from app.models.memory import StyleCardVersion
from app.models.style_card import StyleCard
from app.models.task import Task, TaskPlatform
from app.models.user import User
from app.api.v1.tasks import create_task
from app.schemas.task import TaskCreate
from app.skills.copy_skills import SaveFinalCopySkill


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
        username="content-owner",
        email="content-owner@example.com",
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
    db.add(_current_user())
    db.commit()
    db.close()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _task_and_copy(*, final: bool = True) -> tuple[int, int]:
    db = Session()
    task = Task(
        user_id=1,
        raw_requirement="为新产品生成一篇可审核的头条长文",
        platform=TaskPlatform.TOUTIAO,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    copy = Copy(
        task_id=task.id,
        version=1,
        title="模型初稿",
        content="模型生成的初稿正文",
        platform="toutiao",
        is_final=final,
        applied_style_snapshot={"style_card_id": 9, "version": 3},
        knowledge_citations=[{"source_id": "product-1", "chunk_id": "chunk-2"}],
    )
    db.add(copy)
    db.commit()
    result = (task.id, copy.id)
    db.close()
    return result


def test_task_detail_exposes_independent_execution_content_and_publication_statuses():
    task_id, _ = _task_and_copy()

    response = client.get(f"/api/v1/tasks/{task_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["execution_status"] == "queued"
    assert data["content_status"] == "brief_missing"
    assert data["publication_status"] == "not_prepared"
    assert data["status_reason"] is None


@pytest.mark.parametrize(
    ("legacy_status", "execution_status"),
    [
        ("pending", "queued"),
        ("processing", "running"),
        ("awaiting_human", "waiting_human"),
        ("completed", "succeeded"),
        ("failed", "failed"),
    ],
)
def test_legacy_pipeline_status_updates_the_execution_axis(
    legacy_status: str,
    execution_status: str,
):
    from app.services.task_lifecycle_service import set_task_execution_status

    db = Session()
    task = Task(
        user_id=1,
        raw_requirement="同步旧流水线状态",
        platform=TaskPlatform.WEIBO,
    )
    db.add(task)
    db.commit()

    set_task_execution_status(task, legacy_status)

    assert task.status.value == legacy_status
    assert task.execution_status == execution_status
    assert task.status_updated_at is not None
    db.close()


def test_saved_copy_freezes_task_style_and_citation_snapshots():
    db = Session()
    task = Task(
        user_id=1,
        raw_requirement="保存生成上下文快照",
        platform=TaskPlatform.TOUTIAO,
        orchestration_meta={
            "applied_style_snapshot": {
                "layers": ["platform", "brand", "task"],
                "style_card_id": 7,
                "version": 2,
            },
            "knowledge_citations": [
                {"source_id": "brand-guide", "chunk_id": "brand-guide-4"}
            ],
        },
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    result = SaveFinalCopySkill().execute(
        db,
        task_id=task.id,
        content="依据品牌资料生成的正文",
        platform="toutiao",
        _task_id=task.id,
    )

    assert result["success"] is True
    saved = db.query(Copy).filter(Copy.id == result["copy_id"]).one()
    assert saved.applied_style_snapshot["style_card_id"] == 7
    assert saved.applied_style_snapshot["version"] == 2
    assert saved.knowledge_citations == [
        {"source_id": "brand-guide", "chunk_id": "brand-guide-4"}
    ]
    db.close()


def test_task_creation_freezes_the_active_style_card_version():
    db = Session()
    card = StyleCard(
        topic_cluster="品牌增长",
        platform="toutiao",
        pattern_json={"hook": {"type": "旧规则"}},
        confidence=0.8,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    version = StyleCardVersion(
        style_card_id=card.id,
        version=4,
        pattern_json={"hook": {"type": "反常识"}, "cta_pattern": "评论互动"},
        status="active",
        source_article_ids=["article-1"],
        confidence=0.92,
    )
    db.add(version)
    db.commit()

    result = create_task(
        TaskCreate(
            raw_requirement="写一篇品牌增长的头条深度文章",
            platform=TaskPlatform.TOUTIAO,
            style_card_id=card.id,
        ),
        BackgroundTasks(),
        current_user=_current_user(),
        db=db,
    )

    created = db.query(Task).filter(Task.id == result.data.id).one()
    snapshot = created.orchestration_meta["applied_style_snapshot"]
    assert snapshot["style_card_id"] == card.id
    assert snapshot["version"] == 4
    assert snapshot["pattern"]["hook"]["type"] == "反常识"
    assert snapshot["source_article_ids"] == ["article-1"]
    db.close()


def test_edited_feedback_creates_user_revision_and_moves_content_to_review():
    task_id, copy_id = _task_and_copy()

    response = client.post(
        "/api/v1/memory/feedback",
        json={
            "task_id": task_id,
            "copy_id": copy_id,
            "action": "edited",
            "rating": 1,
            "comment": "缩短标题，并把开头改得更具体",
            "edited_title": "用户修改后的标题",
            "edited_content": "用户修改后的正文",
            "idempotency_key": "content-edit-feedback-1",
        },
    )

    assert response.status_code == 201
    revision_id = response.json()["data"]["result_copy_id"]
    assert revision_id != copy_id
    db = Session()
    revision = db.query(Copy).filter(Copy.id == revision_id).one()
    task = db.query(Task).filter(Task.id == task_id).one()
    assert revision.version == 2
    assert revision.parent_copy_id == copy_id
    assert revision.user_edited is True
    assert revision.title == "用户修改后的标题"
    assert revision.content == "用户修改后的正文"
    assert revision.applied_style_snapshot == {"style_card_id": 9, "version": 3}
    assert revision.change_summary["changed_fields"] == ["title", "content"]
    assert task.content_status == "in_review"
    db.close()


def test_accepted_feedback_approves_selected_version_and_is_idempotent():
    task_id, copy_id = _task_and_copy(final=False)
    payload = {
        "task_id": task_id,
        "copy_id": copy_id,
        "action": "accepted",
        "rating": 1,
        "comment": "采用这一版",
        "idempotency_key": "content-accept-feedback-1",
    }

    first = client.post("/api/v1/memory/feedback", json=payload)
    repeated = client.post("/api/v1/memory/feedback", json=payload)

    assert first.status_code == 201
    assert repeated.status_code == 201
    assert first.json()["data"]["id"] == repeated.json()["data"]["id"]
    db = Session()
    task = db.query(Task).filter(Task.id == task_id).one()
    copy = db.query(Copy).filter(Copy.id == copy_id).one()
    assert task.content_status == "approved"
    assert copy.is_final is True
    assert copy.adopted_at is not None
    db.close()


def test_publish_preparation_moves_only_publication_status_to_ready():
    task_id, copy_id = _task_and_copy()

    response = client.post(
        f"/api/v1/tasks/{task_id}/publish-preparation",
        json={"platform": "toutiao", "copy_id": copy_id},
    )

    assert response.status_code == 200
    db = Session()
    task = db.query(Task).filter(Task.id == task_id).one()
    assert task.publication_status == "ready"
    assert task.content_status == "brief_missing"
    db.close()
