"""记忆系统 P0：租户隔离、索引降级和可信执行上下文。"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.copy import Copy
from app.models.task import Task, TaskPlatform
from app.models.user import User
from app.skills.base import BaseSkill, SkillExecutor, SkillRegistry
from app.skills.copy_skills import SaveFinalCopySkill
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
    row = User(
        username=f"memory-{suffix}",
        email=f"memory-{suffix}@example.com",
        hashed_password="hashed",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _task(db, user: User, topic: str) -> Task:
    row = Task(
        user_id=user.id,
        raw_requirement=f"写一篇关于{topic}的文章",
        platform=TaskPlatform.WEIBO,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _copy(db, task: Task, title: str) -> Copy:
    row = Copy(
        task_id=task.id,
        title=title,
        content=f"共同关键词 {title}",
        platform="weibo",
        review_score=90,
        is_final=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_database_fallback_isolates_current_task_user(db):
    owner = _user(db, "owner")
    stranger = _user(db, "stranger")
    owner_task = _task(db, owner, "AI")
    stranger_task = _task(db, stranger, "AI")
    _copy(db, owner_task, "owner-copy")
    _copy(db, stranger_task, "stranger-copy")

    skill = SearchSimilarCopiesSkill()
    with patch.object(skill, "_search_from_chromadb", side_effect=RuntimeError("offline")):
        result = skill.execute(
            db,
            query_text="共同关键词",
            platform="weibo",
            task_id=owner_task.id,
            limit=5,
        )

    assert result["success"] is True
    assert [item["title"] for item in result["similar_copies"]] == ["owner-copy"]


def test_missing_chroma_collection_falls_back_to_database(db):
    owner = _user(db, "fallback")
    owner_task = _task(db, owner, "降级")
    _copy(db, owner_task, "fallback-copy")

    client = type("MissingCollectionClient", (), {
        "get_collection": lambda self, _name: (_ for _ in ()).throw(RuntimeError("missing"))
    })()
    with patch("chromadb.PersistentClient", return_value=client):
        result = SearchSimilarCopiesSkill().execute(
            db,
            query_text="共同关键词",
            platform="weibo",
            task_id=owner_task.id,
        )

    assert [item["title"] for item in result["similar_copies"]] == ["fallback-copy"]
    assert result["retrieval_source"] == "database_fallback"


class _ContextSkill(BaseSkill):
    seen: dict | None = None

    @property
    def name(self) -> str:
        return "capture_context"

    @property
    def description(self) -> str:
        return "捕获服务端执行上下文"

    @property
    def parameters_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def execute(self, db, **kwargs) -> dict:
        del db
        self.seen = kwargs
        return {"success": True}


def test_skill_executor_injects_trusted_task_context(db):
    skill = _ContextSkill()
    executor = SkillExecutor(SkillRegistry().register(skill))

    result = json.loads(executor.execute(
        "capture_context",
        "{}",
        db,
        task_id=321,
        agent_name="copywriter_agent",
        allowed_function_names={"capture_context"},
    ))

    assert result["success"] is True
    assert skill.seen == {"_task_id": 321, "_agent_name": "copywriter_agent"}


def test_copy_save_survives_temporarily_unavailable_index(db):
    owner = _user(db, "save")
    owner_task = _task(db, owner, "索引")

    result = SaveFinalCopySkill().execute(
        db,
        task_id=owner_task.id,
        _task_id=owner_task.id,
        content="业务数据应先可靠保存，索引可以重试。",
        platform="weibo",
        version=1,
        is_final=True,
    )

    assert result["success"] is True
    assert result["memory_index_status"] in {"pending", "completed"}
    assert db.query(Copy).filter(Copy.task_id == owner_task.id).count() == 1


def test_copy_save_rejects_model_supplied_foreign_task_id(db):
    owner = _user(db, "trusted-owner")
    stranger = _user(db, "trusted-stranger")
    owner_task = _task(db, owner, "自己的任务")
    stranger_task = _task(db, stranger, "别人的任务")

    result = SaveFinalCopySkill().execute(
        db,
        task_id=stranger_task.id,
        _task_id=owner_task.id,
        content="不应写入别人的任务",
        platform="weibo",
    )

    assert result["success"] is False
    assert "上下文" in result["error"]
    assert db.query(Copy).count() == 0
