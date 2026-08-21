"""长期记忆服务：统一处理偏好、反馈、版本激活和上下文预算。"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.copy import Copy
from app.models.memory import MemoryFeedback, MemoryItem, StyleCardVersion, UserPreference
from app.models.style_card import StyleCard
from app.models.task import Task


def upsert_user_preferences(
    db: Session,
    *,
    user_id: int,
    patch: dict[str, Any],
    expected_version: int | None = None,
) -> UserPreference:
    row = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if row is None:
        if expected_version not in (None, 0):
            raise ValueError("偏好版本冲突，请重新读取后再提交")
        row = UserPreference(user_id=user_id, preferences=dict(patch), version=1)
        db.add(row)
    else:
        if expected_version is not None and row.version != expected_version:
            raise ValueError("偏好版本冲突，请重新读取后再提交")
        merged = dict(row.preferences or {})
        merged.update(patch)
        row.preferences = merged
        row.version += 1
    db.commit()
    db.refresh(row)
    for key, value in patch.items():
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        latest = (
            db.query(MemoryItem)
            .filter(
                MemoryItem.user_id == user_id,
                MemoryItem.memory_type == "user_preference",
                MemoryItem.scope_id == "default",
                MemoryItem.source_type == "explicit_preference",
                MemoryItem.source_id == str(key),
            )
            .order_by(MemoryItem.version.desc())
            .first()
        )
        memory = MemoryItem(
            user_id=user_id,
            memory_type="user_preference",
            scope_id="default",
            source_type="explicit_preference",
            source_id=str(key),
            content=f"{key}: {serialized}",
            content_json={"key": key, "value": value},
            content_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            version=(latest.version + 1) if latest else 1,
            status="candidate",
            confidence=1.0,
            quality_score=1.0,
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)
        activate_memory_version(db, memory.id)
    return row


def record_copy_feedback(
    db: Session,
    *,
    user_id: int,
    task_id: int,
    copy_id: int,
    action: str,
    rating: int,
    idempotency_key: str,
    comment: str = "",
    metrics: dict[str, Any] | None = None,
) -> MemoryFeedback:
    existing = (
        db.query(MemoryFeedback)
        .filter(MemoryFeedback.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        if existing.user_id != user_id:
            raise ValueError("无权访问该反馈记录")
        return existing
    owned = (
        db.query(Copy)
        .join(Task, Task.id == Copy.task_id)
        .filter(
            Copy.id == copy_id,
            Copy.task_id == task_id,
            Task.user_id == user_id,
        )
        .first()
    )
    if owned is None:
        raise ValueError("无权为该任务或文案提交反馈")
    if rating not in (-1, 0, 1):
        raise ValueError("rating 只能是 -1、0 或 1")
    row = MemoryFeedback(
        user_id=user_id,
        task_id=task_id,
        copy_id=copy_id,
        action=action,
        rating=rating,
        comment=comment.strip() or None,
        metrics=dict(metrics or {}),
        idempotency_key=idempotency_key,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    feedback_content = comment.strip() or f"用户对文案执行了 {action}，rating={rating}"
    memory = MemoryItem(
        user_id=user_id,
        memory_type="copy_feedback",
        scope_id="default",
        source_type="explicit_feedback",
        source_id=str(copy_id),
        content=feedback_content,
        content_json={"action": action, "rating": rating, "metrics": dict(metrics or {})},
        content_hash=hashlib.sha256(
            f"{action}|{rating}|{feedback_content}".encode("utf-8")
        ).hexdigest(),
        version=(
            db.query(MemoryItem)
            .filter(
                MemoryItem.user_id == user_id,
                MemoryItem.memory_type == "copy_feedback",
                MemoryItem.source_id == str(copy_id),
            )
            .count()
            + 1
        ),
        status="active",
        confidence=1.0,
        quality_score=float((rating + 1) / 2),
    )
    db.add(memory)
    db.commit()
    return row


def activate_memory_version(db: Session, memory_id: int) -> MemoryItem:
    row = db.query(MemoryItem).filter(MemoryItem.id == memory_id).first()
    if row is None:
        raise ValueError("记忆条目不存在")
    previous = (
        db.query(MemoryItem)
        .filter(
            MemoryItem.id != row.id,
            MemoryItem.user_id == row.user_id,
            MemoryItem.memory_type == row.memory_type,
            MemoryItem.scope_id == row.scope_id,
            MemoryItem.source_type == row.source_type,
            MemoryItem.source_id == row.source_id,
            MemoryItem.version < row.version,
            MemoryItem.status.in_(("active", "candidate")),
        )
        .order_by(MemoryItem.version.desc())
        .first()
    )
    if previous is not None:
        previous.status = "superseded"
        row.supersedes_id = previous.id
    row.status = "active"
    db.commit()
    db.refresh(row)
    return row


def save_style_card_version(
    db: Session,
    *,
    style_card: StyleCard,
    pattern: dict[str, Any],
    status: str = "candidate",
    source_article_ids: list[str] | None = None,
    schema_version: int = 1,
) -> StyleCardVersion:
    latest = (
        db.query(StyleCardVersion)
        .filter(StyleCardVersion.style_card_id == style_card.id)
        .order_by(StyleCardVersion.version.desc())
        .first()
    )
    row = StyleCardVersion(
        style_card_id=style_card.id,
        version=(latest.version + 1) if latest else 1,
        pattern_json=dict(pattern),
        status=status,
        schema_version=schema_version,
        source_article_ids=list(source_article_ids or []),
        confidence=float(pattern.get("confidence", 0) or 0),
    )
    if status == "active":
        previous_active = (
            db.query(StyleCardVersion)
            .filter(
                StyleCardVersion.style_card_id == style_card.id,
                StyleCardVersion.status == "active",
            )
            .order_by(StyleCardVersion.version.desc())
            .first()
        )
        if previous_active is not None:
            previous_active.status = "superseded"
            row.supersedes_id = previous_active.id
        style_card.pattern_json = dict(pattern)
        style_card.source_article_ids = list(source_article_ids or [])
        style_card.confidence = row.confidence
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def assemble_memory_context(
    db: Session,
    *,
    user_id: int,
    max_chars: int = 2000,
    max_items: int = 10,
) -> dict[str, Any]:
    now = datetime.utcnow()
    rows = (
        db.query(MemoryItem)
        .filter(
            MemoryItem.user_id == user_id,
            MemoryItem.status == "active",
            or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now),
        )
        .order_by(
            MemoryItem.quality_score.desc(),
            MemoryItem.confidence.desc(),
            MemoryItem.updated_at.desc(),
        )
        .limit(max(1, min(max_items, 50)))
        .all()
    )
    budget = max(0, min(max_chars, 20_000))
    items: list[dict[str, Any]] = []
    parts: list[str] = []
    used = 0
    for row in rows:
        if used >= budget:
            break
        content = row.content[: budget - used]
        if not content:
            break
        items.append({
            "memory_id": row.id,
            "memory_type": row.memory_type,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "content": content,
            "quality_score": float(row.quality_score or 0),
        })
        parts.append(content)
        used += len(content)
    return {"items": items, "text": "\n".join(parts), "total_chars": used}
