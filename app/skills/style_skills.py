"""
风格分析与爆款长文检索 Skill
==============================
- search_hot_articles_by_topic：按话题 + 点赞/阅读排序检索 MySQL 长文
- extract_writing_pattern：从长文提取抽象写作规律（非抄原文）
- get_style_card：读取离线沉淀的风格卡
- save_style_card：将规律写入 style_cards 表（离线/在线沉淀）
"""

from __future__ import annotations

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.models.style_card import StyleCard
from app.models.toutiao_reference import ToutiaoReference
from app.services.writing_pattern_service import extract_writing_pattern_from_articles
from app.skills.base import BaseSkill
from app.utils.logger import logger


def _article_to_dict(row: ToutiaoReference) -> dict:
    return {
        "article_id": row.article_id,
        "title": row.title,
        "content": row.content,
        "keyword": row.keyword or "",
        "like_count": int(row.like_count or 0),
        "read_count": int(row.read_count or 0),
        "comment_count": int(row.comment_count or 0),
        "source_url": row.source_url or "",
    }


class SearchHotArticlesByTopicSkill(BaseSkill):
    """按话题检索最热长文（MySQL 排序，语义检索的补充）。"""

    @property
    def name(self) -> str:
        return "search_hot_articles_by_topic"

    @property
    def description(self) -> str:
        return (
            "从头条长文 MySQL 库中按话题关键词检索爆款长文，"
            "支持按点赞量或阅读量排序。创作前优先调用，"
            "为 extract_writing_pattern 提供输入。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "话题/关键词，如 AI就业",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["likes", "reads", "comments"],
                    "default": "likes",
                    "description": "排序维度：点赞/阅读/评论",
                },
                "limit": {
                    "type": "integer",
                    "default": 3,
                    "description": "返回篇数，最多 5",
                },
            },
            "required": ["topic"],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        topic: str = (kwargs.get("topic") or "").strip()
        sort_by: str = kwargs.get("sort_by", "likes")
        limit: int = min(int(kwargs.get("limit", 3)), 5)

        if not topic:
            return {"success": False, "error": "topic 不能为空", "articles": []}

        like_pattern = f"%{topic}%"
        query = db.query(ToutiaoReference).filter(
            or_(
                ToutiaoReference.keyword.like(like_pattern),
                ToutiaoReference.title.like(like_pattern),
                ToutiaoReference.content.like(like_pattern),
            )
        )

        if sort_by == "reads":
            query = query.order_by(
                desc(ToutiaoReference.read_count),
                desc(ToutiaoReference.like_count),
            )
        elif sort_by == "comments":
            query = query.order_by(
                desc(ToutiaoReference.comment_count),
                desc(ToutiaoReference.like_count),
            )
        else:
            query = query.order_by(
                desc(ToutiaoReference.like_count),
                desc(ToutiaoReference.read_count),
            )

        rows = query.limit(limit).all()
        articles = [_article_to_dict(r) for r in rows]

        # 摘要字段，不把全文传给 Agent（防抄稿）
        summaries = [
            {
                "article_id": a["article_id"],
                "title": a["title"],
                "like_count": a["like_count"],
                "read_count": a["read_count"],
                "keyword": a["keyword"],
                "content_length": len(a.get("content") or ""),
            }
            for a in articles
        ]

        logger.info(
            f"热度长文检索: topic={topic}, sort_by={sort_by}, found={len(articles)}"
        )

        return {
            "success": True,
            "articles": articles,
            "article_summaries": summaries,
            "sort_by": sort_by,
            "message": f"找到 {len(articles)} 篇相关长文（按{sort_by}排序）",
        }


class ExtractWritingPatternSkill(BaseSkill):
    """从爆款长文提取抽象写作规律 JSON。"""

    @property
    def name(self) -> str:
        return "extract_writing_pattern"

    @property
    def description(self) -> str:
        return (
            "从 1～3 篇爆款长文中提取抽象写作规律（标题公式、钩子、篇章结构、节奏、CTA），"
            "禁止抄原文。需先 search_hot_articles_by_topic 或传入 article_ids。"
            "输出 writing_pattern 供 generate_outline 使用。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "话题（无 articles 时自动检索最热长文）",
                },
                "article_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "头条 article_id 列表，最多 3 个",
                },
                "platform": {
                    "type": "string",
                    "description": "目标平台",
                    "default": "weibo",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["likes", "reads", "comments"],
                    "default": "likes",
                },
            },
            "required": [],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        platform = kwargs.get("platform", "weibo")
        article_ids: list[str] = kwargs.get("article_ids") or []
        topic = (kwargs.get("topic") or "").strip()

        articles: list[dict] = []

        if article_ids:
            rows = (
                db.query(ToutiaoReference)
                .filter(ToutiaoReference.article_id.in_(article_ids[:3]))
                .all()
            )
            articles = [_article_to_dict(r) for r in rows]
        elif topic:
            search_result = SearchHotArticlesByTopicSkill().execute(
                db,
                topic=topic,
                sort_by=kwargs.get("sort_by", "likes"),
                limit=3,
            )
            if search_result.get("success"):
                articles = search_result.get("articles", [])

        if not articles:
            return {
                "success": False,
                "error": "未找到可参考的长文，请先导入头条文章或调整话题",
                "writing_pattern": None,
            }

        result = extract_writing_pattern_from_articles(articles, platform=platform)
        if result.get("success"):
            # 不把参考全文返回给 Agent，只返回抽象 pattern
            result["article_ids_used"] = [a.get("article_id") for a in articles]
            result.pop("articles", None)
        return result


class GetStyleCardSkill(BaseSkill):
    """按话题读取离线沉淀的风格卡（若有）。"""

    @property
    def name(self) -> str:
        return "get_style_card"

    @property
    def description(self) -> str:
        return (
            "从 style_cards 库读取已沉淀的抽象写作规律。"
            "若存在匹配话题的风格卡，可跳过实时 extract_writing_pattern。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "话题/关键词"},
                "platform": {"type": "string", "default": "toutiao"},
            },
            "required": ["topic"],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        topic = (kwargs.get("topic") or "").strip()
        platform = kwargs.get("platform", "toutiao")
        if not topic:
            return {"success": False, "error": "topic 不能为空", "writing_pattern": None}

        pattern_like = f"%{topic}%"
        card = (
            db.query(StyleCard)
            .filter(
                StyleCard.platform == platform,
                StyleCard.topic_cluster.like(pattern_like),
            )
            .order_by(desc(StyleCard.avg_like_count), desc(StyleCard.confidence))
            .first()
        )

        if not card:
            return {
                "success": True,
                "found": False,
                "writing_pattern": None,
                "message": "未找到匹配的风格卡，请使用 extract_writing_pattern",
            }

        return {
            "success": True,
            "found": True,
            "style_card_id": card.id,
            "writing_pattern": card.pattern_json,
            "topic_cluster": card.topic_cluster,
            "avg_like_count": card.avg_like_count,
            "message": f"已加载风格卡: {card.topic_cluster}",
        }


class SaveStyleCardSkill(BaseSkill):
    """将 writing_pattern 沉淀为风格卡（供后续复用）。"""

    @property
    def name(self) -> str:
        return "save_style_card"

    @property
    def description(self) -> str:
        return (
            "将 extract_writing_pattern 产出的抽象规律保存到 style_cards 表，"
            "便于同话题下次直接 get_style_card。一般离线脚本调用，Agent 可选。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "topic_cluster": {"type": "string", "description": "话题簇名称"},
                "writing_pattern": {"type": "object", "description": "抽象规律 JSON"},
                "platform": {"type": "string", "default": "toutiao"},
                "avg_like_count": {"type": "integer", "default": 0},
            },
            "required": ["topic_cluster", "writing_pattern"],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        topic_cluster = (kwargs.get("topic_cluster") or "").strip()
        pattern = kwargs.get("writing_pattern")
        if not topic_cluster or not pattern:
            return {"success": False, "error": "topic_cluster 与 writing_pattern 必填"}

        platform = kwargs.get("platform", "toutiao")
        avg_like = int(kwargs.get("avg_like_count", 0))
        confidence = float(pattern.get("confidence", 0) or 0)
        source_ids = pattern.get("source_article_ids")

        existing = (
            db.query(StyleCard)
            .filter(
                StyleCard.topic_cluster == topic_cluster,
                StyleCard.platform == platform,
            )
            .first()
        )
        if existing:
            existing.pattern_json = pattern
            existing.avg_like_count = avg_like
            existing.confidence = confidence
            existing.source_article_ids = source_ids
            db.commit()
            card_id = existing.id
        else:
            card = StyleCard(
                topic_cluster=topic_cluster,
                platform=platform,
                pattern_json=pattern,
                avg_like_count=avg_like,
                confidence=confidence,
                source_article_ids=source_ids,
            )
            db.add(card)
            db.commit()
            db.refresh(card)
            card_id = card.id

        logger.info(f"风格卡已保存: id={card_id}, topic={topic_cluster}")
        return {"success": True, "style_card_id": card_id, "topic_cluster": topic_cluster}
