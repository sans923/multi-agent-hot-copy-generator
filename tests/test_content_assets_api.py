"""内容资产库 API：权限、参考文章入库与风格卡生成。"""

from datetime import datetime

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_admin_user
from app.database import Base, get_db
from app.main import app
from app.models.style_card import StyleCard
from app.models.toutiao_reference import ToutiaoReference
from app.models.user import User
from app.api.v1.tasks import create_task
from app.models.task import Task, TaskPlatform
from app.schemas.task import TaskCreate


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


@pytest.fixture(autouse=True)
def database():
    import app.models as _models  # noqa: F401

    app.dependency_overrides = {get_db: override_db}
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _admin() -> User:
    return User(
        id=1,
        username="admin",
        email="admin@example.com",
        hashed_password="unused",
        is_active=True,
        is_admin=True,
    )


def _as_admin() -> None:
    app.dependency_overrides[get_current_admin_user] = _admin


def test_content_assets_require_admin_authentication():
    response = client.get("/api/v1/content-assets/references")
    assert response.status_code == 401


def test_list_reference_articles_for_admin():
    _as_admin()
    db = Session()
    db.add(ToutiaoReference(
        article_id="123",
        title="一篇参考长文",
        content="正文" * 100,
        keyword="AI就业",
        source_url="https://www.toutiao.com/article/123/",
        embedding_status="completed",
        chunk_count=3,
        created_at=datetime.utcnow(),
    ))
    db.commit()
    db.close()

    response = client.get("/api/v1/content-assets/references")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["article_id"] == "123"
    assert body["items"][0]["content_length"] == 200


def test_import_reference_uses_fetch_and_ingest(monkeypatch):
    _as_admin()
    monkeypatch.setattr(
        "app.services.content_asset_service.fetch_toutiao_article",
        lambda url: {
            "article_id": "456",
            "title": "被导入的文章",
            "content": "有效正文" * 80,
            "source_url": url,
            "author_name": "作者",
        },
    )
    monkeypatch.setattr(
        "app.services.content_asset_service.run_ingest",
        lambda **kwargs: {"chunk_count": 5},
    )

    response = client.post(
        "/api/v1/content-assets/references",
        json={
            "url": "https://www.toutiao.com/article/456/",
            "keyword": "职场",
            "like_count": 120,
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["embedding_status"] == "completed"
    db = Session()
    row = db.query(ToutiaoReference).filter_by(article_id="456").one()
    assert row.chunk_count == 5
    assert row.like_count == 120
    db.close()


def test_build_style_card_from_selected_references(monkeypatch):
    _as_admin()
    db = Session()
    db.add(ToutiaoReference(
        article_id="789",
        title="高赞文章",
        content="参考正文" * 100,
        keyword="AI就业",
        like_count=300,
        embedding_status="completed",
    ))
    db.commit()
    db.close()
    monkeypatch.setattr(
        "app.services.content_asset_service.extract_writing_pattern_from_articles",
        lambda articles, platform: {
            "success": True,
            "writing_pattern": {
                "title_formula": {"pattern": "[身份]+[反差]"},
                "confidence": 0.88,
                "source_article_ids": ["789"],
            },
        },
    )

    response = client.post(
        "/api/v1/content-assets/style-cards",
        json={"topic_cluster": "AI就业", "reference_ids": [1]},
    )

    assert response.status_code == 201
    assert response.json()["data"]["confidence"] == 0.88
    db = Session()
    assert db.query(StyleCard).filter_by(topic_cluster="AI就业").count() == 1
    db.close()


def test_toutiao_task_persists_selected_style_card():
    db = Session()
    admin = _admin()
    db.add(admin)
    card = StyleCard(
        topic_cluster="职业转型",
        platform="toutiao",
        pattern_json={"hook": {"type": "反常识"}},
        confidence=0.9,
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    result = create_task(
        TaskCreate(
            raw_requirement="写一篇职业转型深度长文",
            platform=TaskPlatform.TOUTIAO,
            execution_mode="plan",
            style_card_id=card.id,
        ),
        BackgroundTasks(),
        current_user=admin,
        db=db,
    )

    task = db.query(Task).filter_by(id=result.data.id).one()
    assert task.orchestration_meta["selected_style_card_id"] == card.id
    assert task.orchestration_meta["selected_style_card_topic"] == "职业转型"
    db.close()
