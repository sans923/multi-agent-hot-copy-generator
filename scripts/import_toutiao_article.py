"""
一键导入头条长文：串联【抓取 → MySQL → LangGraph ingest】
==========================================================

【整体三步与 LangGraph 的关系】
    [1/3] fetch_toutiao_article   — 普通 Python，不是 LangGraph
    [2/3] 写 MySQL               — 持久化全文
    [3/3] run_ingest()            — LangGraph 入库图（chunk → index）

用法：
    python scripts/import_toutiao_article.py --url "https://www.toutiao.com/article/7434425099895210546/"
    python scripts/import_toutiao_article.py --url "..." --keyword "AI就业"
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.lang.graph.ingest_graph import run_ingest
from app.lang.toutiao_fetcher import fetch_toutiao_article
from app.models.toutiao_reference import ToutiaoReference


def main() -> None:
    """
    命令行入口：解析参数后顺序执行抓取、入库 MySQL、LangGraph ingest。
    """
    parser = argparse.ArgumentParser(description="导入头条长文到 RAG 向量库")
    parser.add_argument("--url", required=True, help="头条文章 URL")
    parser.add_argument("--keyword", default="", help="采集关键词，便于过滤")
    parser.add_argument("--like-count", type=int, default=0, help="点赞数（手动填入或爬虫获取）")
    parser.add_argument("--read-count", type=int, default=0, help="阅读数")
    parser.add_argument("--comment-count", type=int, default=0, help="评论数")
    args = parser.parse_args()

    # ── 第 1 步：抓取（LangGraph 之前）──
    print(f"[1/3] 抓取: {args.url}")
    data = fetch_toutiao_article(args.url)

    # ── 第 2 步：MySQL 存全文（向量库之前的「源数据」）──
    print(f"[2/3] 写入 MySQL: {data['title'][:50]}...")
    db = SessionLocal()
    try:
        row = db.query(ToutiaoReference).filter(
            ToutiaoReference.article_id == data["article_id"]
        ).first()

        if row:
            row.title = data["title"]
            row.content = data["content"]
            row.author_name = data.get("author_name") or row.author_name
            row.source_url = data["source_url"]
            row.keyword = args.keyword or row.keyword
            row.like_count = args.like_count or row.like_count
            row.read_count = args.read_count or row.read_count
            row.comment_count = args.comment_count or row.comment_count
            row.embedding_status = "pending"
        else:
            row = ToutiaoReference(
                article_id=data["article_id"],
                title=data["title"],
                content=data["content"],
                author_name=data.get("author_name"),
                source_url=data["source_url"],
                keyword=args.keyword,
                like_count=args.like_count,
                read_count=args.read_count,
                comment_count=args.comment_count,
                embedding_status="pending",
            )
            db.add(row)
        db.commit()
        db.refresh(row)
        ref_id = row.id
    finally:
        db.close()

    # ── 第 3 步：LangGraph ingest 图（chunk → index → Chroma）──
    print("[3/3] LangGraph ingest（切块 + 向量化）...")
    ingest_result = run_ingest(
        article_id=data["article_id"],
        title=data["title"],
        content=data["content"],
        source_url=data["source_url"],
        keyword=args.keyword,
        author_name=data.get("author_name") or "",
    )
    chunk_count = ingest_result.get("chunk_count", 0)

    # 回写 MySQL：标记向量入库完成
    db = SessionLocal()
    try:
        row = db.query(ToutiaoReference).filter(ToutiaoReference.id == ref_id).first()
        if row:
            row.embedding_status = "completed"
            row.chunk_count = chunk_count
            db.commit()
    finally:
        db.close()

    print(f"完成: article_id={data['article_id']}, chunks={chunk_count}")


if __name__ == "__main__":
    main()
