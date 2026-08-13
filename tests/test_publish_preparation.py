"""头条辅助发布与抖音 H5 用户确认投稿。"""

from datetime import datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_active_user
from app.database import Base, get_db
from app.main import app
from app.models.copy import Copy
from app.models.task import Task, TaskPlatform, TaskStatus
from app.models.user import User
from app.schemas.publishing import PublishPreparationRequest
from app.services.publishing_service import (
    DouyinOpenPlatformClient,
    DouyinOpenPlatformError,
    build_douyin_h5_schema,
    build_douyin_h5_signature,
    prepare_douyin_publication,
    prepare_toutiao_publication,
)


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


def _user(user_id: int = 1) -> User:
    return User(
        id=user_id,
        username=f"user{user_id}",
        email=f"user{user_id}@example.com",
        hashed_password="unused",
        is_active=True,
        is_admin=False,
    )


@pytest.fixture(autouse=True)
def database():
    import app.models as _models  # noqa: F401

    app.dependency_overrides = {
        get_db: override_db,
        get_current_active_user: _user,
    }
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _persist_final_copy(*, user_id: int = 1) -> tuple[Task, Copy]:
    db = Session()
    user = _user(user_id)
    db.add(user)
    task = Task(
        user_id=user.id,
        raw_requirement="生成一篇可以发布的 AI 长文",
        platform=TaskPlatform.TOUTIAO,
        status=TaskStatus.COMPLETED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(task)
    db.flush()
    copy = Copy(
        task_id=task.id,
        version=2,
        title="AI 时代，普通人如何建立自己的竞争力",
        content="# 开始\n\n这是一篇已经完成审核的长文。",
        hashtags=["AI", "职业成长"],
        platform="toutiao",
        is_final=True,
    )
    db.add(copy)
    db.commit()
    db.refresh(task)
    db.refresh(copy)
    task_id, copy_id = task.id, copy.id
    db.close()
    return Task(id=task_id), Copy(id=copy_id)


def test_toutiao_preparation_builds_copyable_package():
    copy = Copy(
        id=8,
        task_id=3,
        version=2,
        title="测试标题",
        content="测试正文",
        hashtags=["AI", "成长"],
        is_final=True,
    )

    result = prepare_toutiao_publication(copy)

    assert result.ready is True
    assert result.mode == "assisted_export"
    assert result.creator_url == "https://mp.toutiao.com/profile_v4/graphic/publish"
    assert result.package_text == "测试标题\n\n测试正文\n\n#AI #成长"
    assert result.requires_user_confirmation is True


def test_douyin_signature_matches_official_example():
    signature = build_douyin_h5_signature(
        ticket="@ml6sqYBGgTKmQNajnKNkaj8yksCAY++adIhlGIqfTiKyvBqOIkzdJ6WRgP+nO+wtVItqKbX4iZ+mFIYkyPJjpQ==",
        nonce_str="Wm3WZYTPz0wzccnW",
        timestamp="1650941858",
    )

    assert signature == "3f7b739a91a52cb7d85c4f89c5f611fe"


def test_douyin_schema_contains_encoded_submission_material():
    schema = build_douyin_h5_schema(
        client_key="tt-test-key",
        ticket="ticket-value",
        nonce_str="fixed-nonce",
        timestamp="1700000000",
        title="AI 长文摘要",
        hashtags=["AI", "成长"],
        media_url="https://cdn.example.com/cards/cover.jpg",
        media_type="image",
        state="task-9-copy-8",
    )

    parsed = urlparse(schema)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "snssdk1128"
    assert parsed.netloc == "openplatform"
    assert parsed.path == "/share"
    assert query["share_type"] == ["h5"]
    assert query["image_path"] == ["https://cdn.example.com/cards/cover.jpg"]
    assert query["share_to_type"] == ["0"]
    assert query["title"] == ["AI 长文摘要"]
    assert query["hashtag_list"] == ['["AI","成长"]']
    assert query["signature"] == [
        build_douyin_h5_signature("ticket-value", "fixed-nonce", "1700000000")
    ]


def test_douyin_preparation_reports_configuration_blockers():
    copy = Copy(
        id=8,
        task_id=9,
        version=2,
        title="测试标题",
        content="测试正文",
        hashtags=["AI"],
        is_final=True,
    )
    request = PublishPreparationRequest(
        platform="douyin",
        copy_id=8,
        media_url="https://cdn.example.com/video.mp4",
        media_type="video",
    )

    result = prepare_douyin_publication(
        copy,
        request,
        enabled=False,
        client_key="",
        allowed_media_hosts="cdn.example.com",
    )

    assert result.ready is False
    assert result.launch_url is None
    assert "DOUYIN_H5_SHARE_ENABLED" in result.blockers[0]


def test_prepare_toutiao_endpoint_uses_owned_final_copy():
    task, copy = _persist_final_copy()

    response = client.post(
        f"/api/v1/tasks/{task.id}/publish-preparation",
        json={"platform": "toutiao", "copy_id": copy.id},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["copy_id"] == copy.id
    assert data["ready"] is True
    assert data["platform"] == "toutiao"
    assert data["creator_url"].startswith("https://mp.toutiao.com/")


def test_prepare_publication_rejects_foreign_task():
    task, _ = _persist_final_copy(user_id=2)

    response = client.post(
        f"/api/v1/tasks/{task.id}/publish-preparation",
        json={"platform": "toutiao", "copy_id": 1},
    )

    assert response.status_code == 404


def test_prepare_publication_requires_final_copy():
    db = Session()
    user = _user()
    db.add(user)
    task = Task(
        user_id=user.id,
        raw_requirement="尚未生成终稿的任务",
        platform=TaskPlatform.TOUTIAO,
        status=TaskStatus.PROCESSING,
    )
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    response = client.post(
        f"/api/v1/tasks/{task_id}/publish-preparation",
        json={"platform": "toutiao", "copy_id": 1},
    )

    assert response.status_code == 409


def test_prepare_publication_uses_the_selected_final_copy():
    task, older_copy = _persist_final_copy()
    db = Session()
    newer_copy = Copy(
        task_id=task.id,
        version=3,
        title="另一个终稿",
        content="不得替换用户当前选择的终稿",
        hashtags=[],
        platform="toutiao",
        is_final=True,
    )
    db.add(newer_copy)
    db.commit()
    db.close()

    response = client.post(
        f"/api/v1/tasks/{task.id}/publish-preparation",
        json={"platform": "toutiao", "copy_id": older_copy.id},
    )

    assert response.status_code == 200
    assert response.json()["data"]["copy_id"] == older_copy.id


@pytest.mark.parametrize(
    "media_url",
    [
        "https://localhost/cover.jpg",
        "https://127.0.0.1/cover.jpg",
        "https://10.0.0.8/cover.jpg",
        "https://user:password@cdn.example.com/cover.jpg",
    ],
)
def test_douyin_media_url_must_be_public_and_credential_free(media_url):
    with pytest.raises(ValueError):
        PublishPreparationRequest(
            platform="douyin",
            copy_id=8,
            media_url=media_url,
            media_type="image",
        )


def test_douyin_preparation_requires_owned_media_host_allowlist():
    copy = Copy(id=8, task_id=9, title="测试", content="正文", is_final=True)
    request = PublishPreparationRequest(
        platform="douyin",
        copy_id=8,
        media_url="https://attacker.example/cover.jpg",
        media_type="image",
    )

    result = prepare_douyin_publication(
        copy,
        request,
        enabled=True,
        client_key="tt-key",
        ticket="ticket",
        allowed_media_hosts="cdn.example.com",
    )

    assert result.ready is False
    assert result.launch_url is None
    assert "DOUYIN_MEDIA_ALLOWED_HOSTS" in result.blockers[0]


def test_douyin_open_ticket_is_cached(monkeypatch):
    calls = {"token": 0, "ticket": 0}

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, path, json):
            assert path == "/oauth/client_token/"
            assert json["client_secret"] == "server-only-secret"
            calls["token"] += 1
            return FakeResponse(
                {
                    "data": {
                        "error_code": 0,
                        "access_token": "clt",
                        "expires_in": 7200,
                    }
                }
            )

        def get(self, path, headers):
            assert path == "/open/getticket/"
            assert headers == {"access-token": "clt"}
            calls["ticket"] += 1
            return FakeResponse(
                {
                    "data": {
                        "error_code": 0,
                        "ticket": "ticket",
                        "expires_in": 7200,
                    }
                }
            )

    monkeypatch.setattr("app.services.publishing_service.httpx.Client", FakeClient)
    platform_client = DouyinOpenPlatformClient(
        client_key="tt-key",
        client_secret="server-only-secret",
    )

    assert platform_client.get_open_ticket() == "ticket"
    assert platform_client.get_open_ticket() == "ticket"
    assert calls == {"token": 1, "ticket": 1}


def test_douyin_open_platform_error_does_not_expose_client_secret(monkeypatch):
    class FailingClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, _path, json):
            raise httpx.ConnectError(json["client_secret"])

    monkeypatch.setattr("app.services.publishing_service.httpx.Client", FailingClient)
    platform_client = DouyinOpenPlatformClient(
        client_key="tt-key",
        client_secret="never-log-this-secret",
    )

    with pytest.raises(DouyinOpenPlatformError) as exc_info:
        platform_client.get_open_ticket()

    assert "never-log-this-secret" not in str(exc_info.value)
