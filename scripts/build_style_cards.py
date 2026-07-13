"""
离线批量构建风格卡（Style Card）
=================================
从 toutiao_reference 按关键词聚类，提取抽象写作规律并写入 style_cards。

用法：
    python scripts/build_style_cards.py --keyword "AI就业"
    python scripts/build_style_cards.py --all-keywords --min-like 100
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import desc

from app.database import SessionLocal
from app.models.toutiao_reference import ToutiaoReference
from app.services.writing_pattern_service import extract_writing_pattern_from_articles
from app.skills.style_skills import SaveStyleCardSkill


def build_for_keyword(db, keyword: str, limit: int = 3, min_like: int = 0) -> None:
    rows = (
        db.query(ToutiaoReference)
        .filter(ToutiaoReference.keyword.like(f"%{keyword}%"))
        .filter(ToutiaoReference.like_count >= min_like)
        .order_by(desc(ToutiaoReference.like_count))
        .limit(limit)
        .all()
    )
    if not rows:
        print(f"  跳过 {keyword}: 无符合条件长文")
        return

    articles = [
        {
            "article_id": r.article_id,
            "title": r.title,
            "content": r.content,
            "like_count": int(r.like_count or 0),
        }
        for r in rows
    ]
    result = extract_writing_pattern_from_articles(articles, platform="toutiao")
    if not result.get("success"):
        print(f"  失败 {keyword}: {result.get('error')}")
        return

    avg_like = sum(a["like_count"] for a in articles) // len(articles)
    save = SaveStyleCardSkill().execute(
        db,
        topic_cluster=keyword,
        writing_pattern=result["writing_pattern"],
        platform="toutiao",
        avg_like_count=avg_like,
    )
    print(f"  ✓ {keyword} -> style_card_id={save.get('style_card_id')}, avg_like={avg_like}")


def main() -> None:
    parser = argparse.ArgumentParser(description="批量构建风格卡")
    parser.add_argument("--keyword", default="", help="单个关键词")
    parser.add_argument("--all-keywords", action="store_true", help="处理库中所有非空 keyword")
    parser.add_argument("--limit", type=int, default=3, help="每个关键词取几篇长文")
    parser.add_argument("--min-like", type=int, default=0, help="最低点赞过滤")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.keyword:
            build_for_keyword(db, args.keyword, limit=args.limit, min_like=args.min_like)
        elif args.all_keywords:
            keywords = {
                r[0]
                for r in db.query(ToutiaoReference.keyword)
                .filter(ToutiaoReference.keyword.isnot(None))
                .filter(ToutiaoReference.keyword != "")
                .distinct()
                .all()
            }
            print(f"共 {len(keywords)} 个关键词")
            for kw in sorted(keywords):
                build_for_keyword(db, kw, limit=args.limit, min_like=args.min_like)
        else:
            parser.error("请指定 --keyword 或 --all-keywords")
    finally:
        db.close()


if __name__ == "__main__":
    main()
