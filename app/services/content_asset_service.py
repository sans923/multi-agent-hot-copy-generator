"""参考文章与风格卡的应用服务，供 CLI 和 HTTP 入口复用。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.lang.graph.ingest_graph import run_ingest
from app.lang.rag.ingest import delete_article_chunks
from app.lang.toutiao_fetcher import fetch_toutiao_article
from app.models.style_card import StyleCard
from app.models.toutiao_reference import ToutiaoReference
from app.services.writing_pattern_service import extract_writing_pattern_from_articles
from app.services.memory_service import save_style_card_version


def reference_to_dict(row: ToutiaoReference) -> dict[str, Any]:
    return {
        "id": row.id,
        "article_id": row.article_id,
        "title": row.title,
        "author_name": row.author_name,
        "keyword": row.keyword,
        "source_url": row.source_url,
        "like_count": int(row.like_count or 0),
        "read_count": int(row.read_count or 0),
        "comment_count": int(row.comment_count or 0),
        "embedding_status": row.embedding_status,
        "chunk_count": int(row.chunk_count or 0),
        "content_length": len(row.content or ""),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def style_card_to_dict(row: StyleCard) -> dict[str, Any]:
    return {
        "id": row.id,
        "owner_id": row.owner_id,
        "topic_cluster": row.topic_cluster,
        "platform": row.platform,
        "layer": row.layer,
        "priority": int(row.priority or 0),
        "status": row.status,
        "schema_version": int(row.schema_version or 1),
        "pattern_json": row.pattern_json or {},
        "avg_like_count": int(row.avg_like_count or 0),
        "source_article_ids": row.source_article_ids or [],
        "confidence": float(row.confidence or 0),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def import_reference(
    db: Session,
    *,
    url: str,
    keyword: str,
    like_count: int = 0,
    read_count: int = 0,
    comment_count: int = 0,
) -> ToutiaoReference:
    data = fetch_toutiao_article(url)
    row = db.query(ToutiaoReference).filter_by(article_id=data["article_id"]).first()
    if row is None:
        row = ToutiaoReference(article_id=data["article_id"], title=data["title"], content=data["content"])
        db.add(row)
    row.title = data["title"]
    row.content = data["content"]
    row.author_name = data.get("author_name") or row.author_name
    row.source_url = data["source_url"]
    row.keyword = keyword
    row.like_count = like_count
    row.read_count = read_count
    row.comment_count = comment_count
    row.embedding_status = "processing"
    db.commit()
    db.refresh(row)

    try:
        result = run_ingest(
            article_id=row.article_id,
            title=row.title,
            content=row.content,
            source_url=row.source_url or "",
            keyword=row.keyword or "",
            author_name=row.author_name or "",
        )
        row.embedding_status = "completed"
        row.chunk_count = int(result.get("chunk_count", 0) or 0)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        row.embedding_status = "failed"
        db.commit()
        raise


def reindex_reference(db: Session, row: ToutiaoReference) -> ToutiaoReference:
    row.embedding_status = "processing"
    db.commit()
    try:
        result = run_ingest(
            article_id=row.article_id,
            title=row.title,
            content=row.content,
            source_url=row.source_url or "",
            keyword=row.keyword or "",
            author_name=row.author_name or "",
        )
        row.embedding_status = "completed"
        row.chunk_count = int(result.get("chunk_count", 0) or 0)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        row.embedding_status = "failed"
        db.commit()
        raise


def delete_reference(db: Session, row: ToutiaoReference) -> None:
    delete_article_chunks(row.article_id)
    db.delete(row)
    db.commit()


def build_style_card(
    db: Session,
    *,
    topic_cluster: str,
    reference_ids: list[int],
) -> StyleCard:
    rows = db.query(ToutiaoReference).filter(ToutiaoReference.id.in_(reference_ids[:3])).all()
    if not rows:
        raise ValueError("没有找到可用于构建风格卡的参考文章")
    articles = [
        {
            "article_id": row.article_id,
            "title": row.title,
            "content": row.content,
            "like_count": int(row.like_count or 0),
        }
        for row in rows
    ]
    result = extract_writing_pattern_from_articles(articles, platform="toutiao")
    if not result.get("success"):
        raise ValueError(result.get("error") or "写作规律提取失败")
    pattern = result["writing_pattern"]
    avg_like = sum(article["like_count"] for article in articles) // len(articles)
    card = db.query(StyleCard).filter_by(topic_cluster=topic_cluster, platform="toutiao").first()
    if card is None:
        card = StyleCard(topic_cluster=topic_cluster, platform="toutiao", pattern_json=pattern)
        db.add(card)
    card.pattern_json = pattern
    card.avg_like_count = avg_like
    card.source_article_ids = [row.article_id for row in rows]
    card.confidence = float(pattern.get("confidence", 0) or 0)
    db.commit()
    db.refresh(card)
    save_style_card_version(
        db,
        style_card=card,
        pattern=pattern,
        status="active",
        source_article_ids=[row.article_id for row in rows],
    )
    return card
