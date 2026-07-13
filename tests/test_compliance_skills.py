"""
合规 Skill 与统一返回格式测试
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.toutiao_reference import ToutiaoReference
from app.skills.base import SkillExecutor, SkillRegistry
from app.skills.compliance_skills import (
    CheckPlagiarismOverlapSkill,
    CheckSensitiveWordsSkill,
)
from app.skills.skill_response import normalize_skill_result, skill_ok


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


def test_skill_ok_envelope():
    raw = skill_ok({"passed": True, "hit_count": 0}, message="ok")
    assert raw["success"] is True
    assert raw["data"]["passed"] is True


def test_normalize_skill_result_legacy_shape():
    legacy = {"success": True, "total_score": 85, "need_optimization": False}
    normalized = normalize_skill_result(legacy, "review_copy_quality", 120.5)
    assert normalized["success"] is True
    assert normalized["data"]["total_score"] == 85
    assert normalized["total_score"] == 85
    assert normalized["meta"]["skill"] == "review_copy_quality"


def test_skill_executor_normalizes_output(db):
    registry = SkillRegistry()
    registry.register(CheckSensitiveWordsSkill())
    executor = SkillExecutor(registry)

    result_json = executor.execute(
        "check_sensitive_words",
        json.dumps({"text": "这是一篇正常文案，无违规内容", "platform": "weibo"}),
        db=db,
    )
    parsed = json.loads(result_json)
    assert parsed["success"] is True
    assert parsed["passed"] is True
    assert "data" in parsed
    assert "meta" in parsed
    assert parsed["meta"]["skill"] == "check_sensitive_words"


def test_check_sensitive_words_hits(db):
    result = CheckSensitiveWordsSkill().execute(
        db,
        text="这是最好的产品，日赚万元不是梦",
        platform="weibo",
    )
    assert result["success"] is True
    assert result["data"]["passed"] is False
    assert result["data"]["hit_count"] >= 2


def test_check_plagiarism_overlap_with_reference(db):
    ref_text = "这是一段非常长的参考文章内容用于测试重叠检测功能必须足够长"
    db.add(ToutiaoReference(
        article_id="ref1",
        title="参考",
        content=ref_text,
        keyword="测试",
        like_count=1000,
    ))
    db.commit()

    draft = ref_text + "后面是少量原创补充内容"
    result = CheckPlagiarismOverlapSkill().execute(
        db, text=draft, topic="测试", ngram_len=10
    )
    assert result["success"] is True
    assert result["data"]["passed"] is False
    assert result["data"]["need_rewrite"] is True


def test_check_plagiarism_clean_text(db):
    db.add(ToutiaoReference(
        article_id="ref2",
        title="AI",
        content="完全不同的参考文章内容关于人工智能发展趋势分析",
        keyword="AI",
        like_count=100,
    ))
    db.commit()

    result = CheckPlagiarismOverlapSkill().execute(
        db,
        text="今天聊聊职场成长，保持学习节奏很重要。",
        topic="AI",
    )
    assert result["success"] is True
    assert result["data"]["passed"] is True
