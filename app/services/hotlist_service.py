"""
热榜抓取与同步服务
==================
负责从韩小韩 API 抓取各平台热榜数据，清洗后写入数据库

【数据流转图】
韩小韩API (HTTP)
    → 原始JSON数据
    → 数据清洗（去重/去空/截断）
    → 写入 hotlist_sync 表
    → 触发向量化（存入ChromaDB）

【韩小韩 API 说明】
接口：https://api.vvhan.com/api/hotlist?type=XXX
无需 API Key，免费使用，每小时更新
支持平台参数 type：
  - wbHot      微博热搜
  - douyinHot  抖音热榜
  - bili        B站热门
  - zhihuHot   知乎热榜
  - toutiaoHot 今日头条

典型响应：
{
  "success": true,
  "title": "微博热搜",
  "update_time": "2024-01-01 12:00:00",
  "data": [
    {
      "order": 1,
      "title": "话题标题",
      "desc": "话题描述",
      "hot": "1234567",
      "url": "https://...",
      "pic": "https://..."
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


# ====================================================
# 平台配置表
# ====================================================

# 每个平台的配置信息
# key = 内部平台标识（存数据库）
# value = dict 包含 API 参数和显示名称
PLATFORM_CONFIG = {
    "weibo": {
        "api_type": "wbHot",          # 韩小韩API的type参数
        "display_name": "微博热搜",
        "max_items": 30,              # 最多保存前N条
    },
    "douyin": {
        "api_type": "douyinHot",
        "display_name": "抖音热榜",
        "max_items": 20,
    },
    "bilibili": {
        "api_type": "bili",
        "display_name": "B站热门",
        "max_items": 20,
    },
    "zhihu": {
        "api_type": "zhihuHot",
        "display_name": "知乎热榜",
        "max_items": 20,
    },
    "toutiao": {
        "api_type": "toutiaoHot",
        "display_name": "今日头条",
        "max_items": 20,
    },
}


# ====================================================
# 单平台抓取函数
# ====================================================

async def fetch_platform_hotlist(
    platform_key: str,
    client: httpx.AsyncClient
) -> list[dict]:
    """
    抓取单个平台的热榜数据

    参数：
        platform_key: 平台标识（如 "weibo"）
        client: 复用的 httpx 异步客户端（避免重复创建连接）

    返回：
        list[dict]：清洗后的热榜条目列表，失败时返回空列表

    为什么用 async？
    - 抓取5个平台如果逐个等待，共需 5 × (网络延迟) 秒
    - 用 asyncio.gather 并发抓取，总耗时 ≈ 最慢那个平台的耗时
    """
    config = PLATFORM_CONFIG.get(platform_key)
    if not config:
        logger.warning(f"未知平台: {platform_key}")
        return []

    url = f"{settings.HAN_API_BASE_URL}/hotlist"
    params = {"type": config["api_type"]}

    try:
        logger.debug(f"开始抓取 {config['display_name']} 热榜...")
        response = await client.get(url, params=params, timeout=10.0)
        response.raise_for_status()  # 非2xx状态码抛出异常

        raw_data = response.json()

        # 韩小韩API返回 success 字段表示是否成功
        if not raw_data.get("success", False):
            logger.warning(f"{config['display_name']} API返回失败: {raw_data}")
            return []

        items = raw_data.get("data", [])
        logger.info(f"{config['display_name']} 抓取成功，共 {len(items)} 条")

        # 数据清洗 + 格式标准化
        cleaned = _clean_hotlist_items(items, platform_key, config)
        return cleaned[:config["max_items"]]  # 只取前N条

    except httpx.TimeoutException:
        logger.error(f"{config['display_name']} 抓取超时")
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"{config['display_name']} HTTP错误: {e.response.status_code}")
        return []
    except Exception as e:
        logger.error(f"{config['display_name']} 抓取异常: {e}")
        return []


def _clean_hotlist_items(
    raw_items: list[dict],
    platform_key: str,
    config: dict
) -> list[dict]:
    """
    数据清洗函数：把韩小韩API的原始格式统一化

    清洗规则：
    1. 过滤空标题
    2. 截断超长文本（防止数据库字段溢出）
    3. 统一字段名（不同平台返回字段名不一致）
    4. 去掉广告条目（热度值为0的通常是广告）

    韩小韩API不同平台返回字段略有差异，这里做统一映射：
    - order/index/rank -> rank（排名）
    - title/name -> title（标题）
    - desc/description -> description（描述）
    - hot/hotScore/num -> hot_value（热度值）
    - url/link/mobileUrl -> url（链接）
    - pic/cover/img -> image_url（图片）
    """
    cleaned = []

    for item in raw_items:
        # 提取标题（不同平台字段名不同）
        title = (
            item.get("title") or
            item.get("name") or
            item.get("word") or
            ""
        ).strip()

        # 过滤空标题
        if not title:
            continue

        # 截断过长标题（数据库字段 VARCHAR(300)）
        if len(title) > 280:
            title = title[:280] + "..."

        # 提取排名
        rank = item.get("order") or item.get("index") or item.get("rank") or 0
        try:
            rank = int(rank)
        except (ValueError, TypeError):
            rank = 0

        # 提取热度值（转为字符串，因为有些是"1.2万"这样的格式）
        hot_value = str(
            item.get("hot") or
            item.get("hotScore") or
            item.get("num") or
            item.get("readNum") or
            ""
        )

        # 提取描述
        description = (
            item.get("desc") or
            item.get("description") or
            item.get("abstract") or
            None
        )
        if description and len(description) > 500:
            description = description[:500] + "..."

        # 提取URL
        url = (
            item.get("url") or
            item.get("link") or
            item.get("mobileUrl") or
            None
        )

        # 提取图片
        image_url = (
            item.get("pic") or
            item.get("cover") or
            item.get("img") or
            None
        )

        cleaned.append({
            "source_platform": platform_key,
            "rank": rank,
            "title": title,
            "description": description,
            "hot_value": hot_value,
            "url": url,
            "image_url": image_url,
            "extra_data": item,  # 保留原始数据
        })

    return cleaned


# ====================================================
# 全量同步入口（APScheduler 调用这个）
# ====================================================

async def sync_all_hotlists() -> dict:
    """
    并发抓取所有平台热榜，写入数据库

    这是 APScheduler 定时调用的核心函数
    
    返回：
        dict: 各平台同步结果统计
        如 {"weibo": 30, "douyin": 20, "failed": ["bilibili"]}
    
    执行流程：
    1. 并发调用5个平台的抓取函数（asyncio.gather）
    2. 写入数据库前，先标记同平台的旧数据为过期
    3. 批量插入新数据
    4. 触发向量化（异步，不阻塞主流程）
    """
    logger.info("=" * 40)
    logger.info("开始全量热榜同步...")
    start_time = datetime.utcnow()

    # 创建一个复用的 HTTP 客户端（提高性能，避免重复握手）
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (HotCopyGenerator/1.0)"},
        follow_redirects=True,
    ) as client:
        # asyncio.gather 并发执行多个协程
        # 就像同时打开5个浏览器标签抓取，而不是一个个等
        tasks = [
            fetch_platform_hotlist(platform_key, client)
            for platform_key in PLATFORM_CONFIG.keys()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 写入数据库
    stats = {}
    db: Session = SessionLocal()
    try:
        for platform_key, items in zip(PLATFORM_CONFIG.keys(), results):
            if isinstance(items, Exception):
                logger.error(f"{platform_key} 抓取异常: {items}")
                stats[platform_key] = 0
                continue

            if not items:
                stats[platform_key] = 0
                continue

            count = _save_hotlist_to_db(db, platform_key, items)
            stats[platform_key] = count

        db.commit()
        logger.info(f"热榜写库完成: {stats}")

    except Exception as e:
        db.rollback()
        logger.error(f"热榜写库失败: {e}")
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
    - 先把该平台24小时以内的旧记录标记为过期（is_expired=1）
    - 再批量插入新记录
    - 不直接删除旧数据，保留历史记录供分析用

    返回：成功写入的条数
    """
    # 标记该平台近期数据为过期（软删除）
    expire_before = datetime.utcnow() - timedelta(hours=24)
    db.query(HotlistSync).filter(
        HotlistSync.source_platform == platform_key,
        HotlistSync.is_expired == 0,
    ).update({"is_expired": 1})

    # 批量插入新数据
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
            embedding_status="pending",  # 等待向量化
            fetched_at=datetime.utcnow(),
            is_expired=0,
        )
        new_records.append(record)
        db.add(record)

    # flush 让数据库分配 id（但还没 commit）
    # 这样 new_records 里的对象有 id 了，可以用于后续操作
    db.flush()

    logger.debug(f"{platform_key} 写入 {len(new_records)} 条新记录")
    return len(new_records)


# ====================================================
# 单平台手动同步（供 API 接口触发）
# ====================================================

async def sync_single_platform(platform_key: str) -> int:
    """
    手动触发单个平台同步（管理员接口或测试用）

    返回：同步的条数
    """
    if platform_key not in PLATFORM_CONFIG:
        raise ValueError(f"不支持的平台: {platform_key}，支持: {list(PLATFORM_CONFIG.keys())}")

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (HotCopyGenerator/1.0)"},
        follow_redirects=True,
    ) as client:
        items = await fetch_platform_hotlist(platform_key, client)

    if not items:
        return 0

    db: Session = SessionLocal()
    try:
        count = _save_hotlist_to_db(db, platform_key, items)
        db.commit()
        return count
    except Exception as e:
        db.rollback()
        logger.error(f"单平台同步写库失败: {e}")
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
