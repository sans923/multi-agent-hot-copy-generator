"""发布效果真源、重复证据偏好晋升与当前用户洞察。"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.copy import Copy
from app.models.memory import MemoryFeedback, MemoryItem, PublicationRecord
from app.models.task import Task


POSITIVE_ACTIONS = {"accepted", "edited", "published"}


def promote_repeated_preferences(db: Session, *, user_id: int, threshold: int = 3) -> list[MemoryItem]:
    """仅把重复、正向、结构化风格信号晋升为 active 记忆。"""
    feedback_rows = (
        db.query(MemoryFeedback)
        .filter(MemoryFeedback.user_id == user_id, MemoryFeedback.rating >= 0)
        .order_by(MemoryFeedback.id)
        .all()
    )
    evidence: dict[tuple[str, str], list[int]] = {}
    values: dict[tuple[str, str], Any] = {}
    for row in feedback_rows:
        if row.action not in POSITIVE_ACTIONS:
            continue
        signals = dict((row.metrics or {}).get("style_signals") or {})
        for key, value in signals.items():
            stable = json.dumps(value, ensure_ascii=False, sort_keys=True)
            evidence.setdefault((str(key), stable), []).append(row.id)
            values[(str(key), stable)] = value

    promoted: list[MemoryItem] = []
    for (key, stable), feedback_ids in evidence.items():
        if len(feedback_ids) < threshold:
            continue
        source_id = hashlib.sha256(f"{key}|{stable}".encode("utf-8")).hexdigest()[:32]
        row = (
            db.query(MemoryItem)
            .filter(
                MemoryItem.user_id == user_id,
                MemoryItem.memory_type == "inferred_preference",
                MemoryItem.source_type == "feedback_aggregate",
                MemoryItem.source_id == source_id,
                MemoryItem.status == "active",
            )
            .first()
        )
        payload = {
            "preference_key": key,
            "preference_value": values[(key, stable)],
            "sample_count": len(feedback_ids),
            "feedback_ids": feedback_ids[-20:],
        }
        content = f"重复采用的风格偏好：{key}={stable}（{len(feedback_ids)} 次证据）"
        if row is None:
            row = MemoryItem(
                user_id=user_id,
                memory_type="inferred_preference",
                scope_id=key,
                source_type="feedback_aggregate",
                source_id=source_id,
                content=content,
                content_json=payload,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                status="active",
                version=1,
                confidence=min(0.95, 0.5 + len(feedback_ids) * 0.1),
                quality_score=min(1.0, len(feedback_ids) / max(threshold, 5)),
            )
            db.add(row)
        else:
            row.content = content
            row.content_json = payload
            row.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            row.confidence = min(0.95, 0.5 + len(feedback_ids) * 0.1)
            row.quality_score = min(1.0, len(feedback_ids) / max(threshold, 5))
        promoted.append(row)
    db.commit()
    return promoted


def record_publication(
    db: Session, *, user_id: int, task_id: int, copy_id: int, platform: str,
    publication_status: str, idempotency_key: str, external_id: str | None = None,
    url: str | None = None, metrics: dict[str, float] | None = None,
) -> PublicationRecord:
    existing = db.query(PublicationRecord).filter_by(user_id=user_id, idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing
    owned = (
        db.query(Copy)
        .join(Task, Task.id == Copy.task_id)
        .filter(Copy.id == copy_id, Copy.task_id == task_id, Task.user_id == user_id)
        .first()
    )
    if owned is None:
        raise ValueError("无权记录该任务或文案的发布结果")
    now = datetime.utcnow()
    row = PublicationRecord(
        user_id=user_id, task_id=task_id, copy_id=copy_id, platform=platform,
        status=publication_status, external_id=external_id, url=url,
        metrics=dict(metrics or {}), idempotency_key=idempotency_key,
        published_at=now if publication_status == "published" else None,
        metrics_updated_at=now if metrics else None,
    )
    db.add(row)
    task = db.query(Task).filter_by(id=task_id).one()
    if publication_status == "published":
        task.publication_status = "published"
        task.status_reason = None
        task.status_updated_at = now
    db.commit()
    db.refresh(row)
    return row


def update_publication_metrics(
    db: Session, *, user_id: int, publication_id: int, metrics: dict[str, float],
) -> PublicationRecord:
    row = db.query(PublicationRecord).filter_by(id=publication_id, user_id=user_id).first()
    if row is None:
        raise ValueError("发布记录不存在或无权访问")
    row.metrics = dict(metrics)
    row.metrics_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def build_memory_insights(db: Session, *, user_id: int) -> dict[str, Any]:
    feedback = db.query(MemoryFeedback).filter_by(user_id=user_id).all()
    total = len(feedback)
    adopted = sum(1 for row in feedback if row.action in {"accepted", "edited", "published"})
    edited = sum(1 for row in feedback if row.action == "edited")
    rejected = sum(1 for row in feedback if row.action == "rejected")
    publications = db.query(PublicationRecord).filter_by(user_id=user_id).all()
    metric_totals: dict[str, float] = {}
    for publication in publications:
        for key, value in dict(publication.metrics or {}).items():
            if isinstance(value, (int, float)):
                metric_totals[key] = metric_totals.get(key, 0.0) + float(value)
    inferred = db.query(MemoryItem).filter_by(
        user_id=user_id, memory_type="inferred_preference", status="active"
    ).count()
    return {
        "feedback": {
            "total": total,
            "adoption_rate": round(adopted / total, 4) if total else 0.0,
            "edit_rate": round(edited / total, 4) if total else 0.0,
            "rejection_rate": round(rejected / total, 4) if total else 0.0,
        },
        "publication": {"total": len(publications), "metrics": metric_totals},
        "memory": {"active_inferred_preferences": inferred},
    }
