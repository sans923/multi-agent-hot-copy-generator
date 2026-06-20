"""
热榜抓取与同步服务
==================
负责从聚合数据 API 抓取网络热点数据，清洗后写入数据库

【数据流转图】
聚合数据API (HTTP)
    → 原始JSON数据
    → 数据清洗（去重/去空/截断）
    → 写入 hotlist_sync 表
    → 触发向量化（存入ChromaDB）

【聚合数据热榜 API 说明】
接口：https://apis.juhe.cn/fapigx/networkhot/query
请求方式：GET
需要 API Key（在 .env 中配置 JUHE_API_KEY）

典型响应：
{
  "resultcode": "200",
  "reason": "Success",
  "result": [
    {
      "hotnum": 123456,
      "title": "话题标题",
      "digest": "话题简介"
    }
  ]
}
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.hotlist_sync import HotlistSync
from app.utils.logger import logger

# 聚合数据平台标识（存数据库用）
JUHE_PLATFORM_KEY = "juhe"
JUHE_MAX_ITEMS = 50  # 最多保存前50条


# ====================================================
# 热榜抓取函数
# ====================================================

async def fetch_juhe_hotlist(client: httpx.AsyncClient) -> list[dict]:
    """
    从聚合数据 API 抓取综合热榜数据

    参数：
        client: 复用的 httpx 异步客户端

    返回：
        list[dict]：清洗后的热榜条目列表，失败时返回空列表
    """
    if not settings.JUHE_API_KEY:
        logger.warning("JUHE_API_KEY 未配置，跳过热榜同步。请在 .env 中设置 JUHE_API_KEY")
        return []

    url = settings.JUHE_HOTLIST_URL
    params = {"key": settings.JUHE_API_KEY}

    try:
        logger.debug(f"开始抓取聚合数据热榜，URL: {url}")
        response = await client.get(url, params=params, timeout=10.0)
        response.raise_for_status()

        raw_data = response.json()
        logger.info(f"聚合数据热榜原始响应: {raw_data}")

        # 聚合数据成功标志：error_code == 0
        # （部分错误响应也会带 resultcode 字段，但成功时只用 error_code 判断）
        error_code = raw_data.get("error_code")
        if error_code != 0:
            logger.warning(
                f"聚合数据热榜 API 返回失败: "
                f"error_code={error_code}, "
                f"reason={raw_data.get('reason')}, "
                f"完整响应={raw_data}"
            )
            return []

        result = raw_data.get("result")

        # 兼容聚合数据三种返回格式：
        # - 直接列表：[{"title": ..., "hotnum": ..., "digest": ...}, ...]
        # - 带list键的对象：{"list": [...]}   ← 实际返回的是这种
        # - 单个对象：{"title": ..., "hotnum": ..., "digest": ...}
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            if "list" in result:
                items = result["list"]   # 真实格式：result.list 才是数组
            else:
                items = [result]
        else:
            logger.warning(f"聚合数据热榜 result 格式未知: {type(result).__name__}，值={result}")
            return []

        if not items:
            logger.warning("聚合数据热榜返回空结果")
            return []

        logger.info(f"聚合数据热榜抓取成功，共 {len(items)} 条")
        cleaned = _clean_juhe_items(items)
        return cleaned[:JUHE_MAX_ITEMS]

    except httpx.TimeoutException as e:
        logger.error(f"聚合数据热榜抓取超时: {type(e).__name__}: {repr(e)}")
        return []
    except httpx.HTTPStatusError as e:
        logger.error(
            f"聚合数据热榜 HTTP 错误: 状态码={e.response.status_code}, 详情: {repr(e)}"
        )
        return []
    except Exception as e:
        logger.error(f"聚合数据热榜抓取异常: {type(e).__name__}: {repr(e)}")
        return []


def _clean_juhe_items(raw_items: list[dict]) -> list[dict]:
    """
    数据清洗：把聚合数据 API 的原始格式转换为统一的内部格式

    聚合数据字段映射：
    - title   -> title（话题标题）
    - digest  -> description（话题简介，可能为空）
    - hotnum  -> hot_value（热搜指数）
    """
    cleaned = []

    for idx, item in enumerate(raw_items):
        title = (item.get("title") or "").strip()
        if not title:
            continue

        if len(title) > 280:
            title = title[:280] + "..."

        description = item.get("digest") or None
        if description and len(description) > 500:
            description = description[:500] + "..."

        hot_value = str(item.get("hotnum") or "")

        cleaned.append({
            "source_platform": JUHE_PLATFORM_KEY,
            "rank": idx + 1,          # 聚合数据没有排名字段，用顺序代替
            "title": title,
            "description": description,
            "hot_value": hot_value,
            "url": None,
            "image_url": None,
            "extra_data": item,
        })

    return cleaned


# ====================================================
# 全量同步入口（APScheduler 调用这个）
# ====================================================

async def sync_all_hotlists() -> dict:
    """
    抓取聚合数据热榜，写入数据库

    这是 APScheduler 定时调用的核心函数

    返回：
        dict: 同步结果统计，如 {"juhe": 50}
    """
    logger.info("=" * 40)
    logger.info("开始全量热榜同步...")
    start_time = datetime.utcnow()

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (HotCopyGenerator/1.0)"},
        follow_redirects=True,
    ) as client:
        items = await fetch_juhe_hotlist(client)

    stats = {}
    db: Session = SessionLocal()
    try:
        if items:
            count = _save_hotlist_to_db(db, JUHE_PLATFORM_KEY, items)
            stats[JUHE_PLATFORM_KEY] = count
        else:
            stats[JUHE_PLATFORM_KEY] = 0

        db.commit()
        logger.info(f"热榜写库完成: {stats}")

    except Exception as e:
        db.rollback()
        logger.error(f"热榜写库失败: {type(e).__name__}: {repr(e)}")
    finally:
        db.close()

    elapsed = (datetime.utcnow() - start_time).total_seconds()
    logger.info(f"热榜同步完成，耗时 {elapsed:.2f}s，结果: {stats}")
    logger.info("=" * 40)

    return stats


def _save_hotlist_to_db(
    db: Session,
    platform_key: str,
    items: list[dict]
) -> int:
    """
    将热榜数据写入数据库

    策略：
    - 先把该平台旧记录标记为过期（is_expired=1）
    - 再批量插入新记录
    - 不直接删除旧数据，保留历史记录供分析用

    返回：成功写入的条数
    """
    db.query(HotlistSync).filter(
        HotlistSync.source_platform == platform_key,
        HotlistSync.is_expired == 0,
    ).update({"is_expired": 1})

    new_records = []
    for item in items:
        record = HotlistSync(
            source_platform=item["source_platform"],
            rank=item["rank"],
            title=item["title"],
            description=item.get("description"),
            hot_value=item.get("hot_value"),
            url=item.get("url"),
            image_url=item.get("image_url"),
            extra_data=item.get("extra_data"),
            embedding_status="pending",
            fetched_at=datetime.utcnow(),
            is_expired=0,
        )
        new_records.append(record)
        db.add(record)

    db.flush()
    logger.debug(f"{platform_key} 写入 {len(new_records)} 条新记录")
    return len(new_records)


# ====================================================
# 手动同步（供 API 接口触发）
# ====================================================

async def sync_single_platform(platform_key: str) -> int:
    """
    手动触发热榜同步（管理员接口或测试用）
    platform_key 参数保留以兼容旧接口，现在只支持 juhe

    返回：同步的条数
    """
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (HotCopyGenerator/1.0)"},
        follow_redirects=True,
    ) as client:
        items = await fetch_juhe_hotlist(client)

    if not items:
        return 0

    db: Session = SessionLocal()
    try:
        count = _save_hotlist_to_db(db, JUHE_PLATFORM_KEY, items)
        db.commit()
        return count
    except Exception as e:
        db.rollback()
        logger.error(f"手动同步写库失败: {type(e).__name__}: {repr(e)}")
        return 0
    finally:
        db.close()


# ====================================================
# 热榜查询（供 Agent 调用）
# ====================================================

def get_recent_hotlist(
    db: Session,
    platform: Optional[str] = None,
    limit: int = 20,
    include_expired: bool = False
) -> list[HotlistSync]:
    """
    查询最新有效热榜数据

    参数：
        platform: 平台过滤（None=全部平台）
        limit: 返回条数
        include_expired: 是否包含过期数据（默认只返回最新的）

    这个函数后续会被 Agent 的 Skill 调用
    """
    query = db.query(HotlistSync)

    if not include_expired:
        query = query.filter(HotlistSync.is_expired == 0)

    if platform:
        query = query.filter(HotlistSync.source_platform == platform)

    return (
        query
        .order_by(HotlistSync.fetched_at.desc(), HotlistSync.rank.asc())
        .limit(limit)
        .all()
    )
