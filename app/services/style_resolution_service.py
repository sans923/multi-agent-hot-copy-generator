"""确定性合并平台、品牌、账号和任务风格，输出可冻结快照。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.memory import StyleCardVersion, UserPreference
from app.models.style_card import StyleCard


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if key == "banned_terms":
            existing = list(result.get(key) or [])
            for term in list(value or []):
                if term not in existing:
                    existing.append(term)
            result[key] = existing
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def resolve_style_snapshot(
    db: Session,
    *,
    user_id: int,
    platform: str,
    selected_style_card_id: int | None = None,
    task_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    layers: list[dict[str, Any]] = []
    pattern: dict[str, Any] = {}

    platform_cards = (
        db.query(StyleCard)
        .filter(
            StyleCard.owner_id.is_(None),
            StyleCard.platform == platform,
            StyleCard.layer == "platform",
            StyleCard.status == "active",
        )
        .order_by(StyleCard.priority, StyleCard.id)
        .all()
    )
    for card in platform_cards:
        pattern = _deep_merge(pattern, dict(card.pattern_json or {}))
        layers.append({"layer": "platform", "style_card_id": card.id, "version": 0})

    preference = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if preference and preference.preferences:
        brand_pattern: dict[str, Any] = {}
        for key in ("brand_voice", "banned_terms", "preferred_terms", "audience"):
            if key in preference.preferences:
                brand_pattern[key] = preference.preferences[key]
        if brand_pattern:
            pattern = _deep_merge(pattern, brand_pattern)
            layers.append({"layer": "brand", "preference_version": preference.version})

    selected_version = 0
    selected_sources: list[str] = []
    selected_confidence = 0.0
    if selected_style_card_id is not None:
        card = (
            db.query(StyleCard)
            .filter(
                StyleCard.id == selected_style_card_id,
                or_(StyleCard.owner_id == user_id, StyleCard.owner_id.is_(None)),
                StyleCard.platform == platform,
                StyleCard.status == "active",
            )
            .first()
        )
        if card is None:
            raise ValueError("指定风格卡不存在、未激活或无权使用")
        version = (
            db.query(StyleCardVersion)
            .filter(
                StyleCardVersion.style_card_id == card.id,
                StyleCardVersion.status == "active",
            )
            .order_by(StyleCardVersion.version.desc())
            .first()
        )
        selected_version = version.version if version else 0
        selected_sources = list(version.source_article_ids if version else (card.source_article_ids or []))
        selected_confidence = float(version.confidence if version else (card.confidence or 0))
        selected_pattern = dict(version.pattern_json if version else card.pattern_json or {})
        pattern = _deep_merge(pattern, selected_pattern)
        layers.append({"layer": card.layer, "style_card_id": card.id, "version": selected_version})

    if task_override:
        pattern = _deep_merge(pattern, dict(task_override))
        layers.append({"layer": "task", "version": 1})

    return {
        "platform": platform,
        "pattern": pattern,
        "layers": layers,
        "selected_style_card_id": selected_style_card_id,
        "selected_style_version": selected_version,
        "style_card_id": selected_style_card_id,
        "version": selected_version,
        "source_article_ids": selected_sources,
        "confidence": selected_confidence,
        "schema_version": 1,
    }
