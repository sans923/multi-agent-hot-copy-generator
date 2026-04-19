"""
APScheduler 定时任务模块
========================
负责管理所有后台定时任务

【APScheduler 核心概念】
--------------------------
- Scheduler（调度器）：任务的总管，负责启动/停止/管理所有任务
- Job（任务）：被调度的函数
- Trigger（触发器）：决定任务何时执行
  * IntervalTrigger：每隔 X 秒/分/小时执行一次
  * CronTrigger：像 Linux cron 一样，指定时间点执行（如每天8点）
  * DateTrigger：只执行一次，在指定时间点

【为什么用 AsyncIOScheduler？】
FastAPI 是基于 asyncio 的异步框架
AsyncIOScheduler 和 asyncio 共享同一个事件循环
普通的 BackgroundScheduler 是多线程的，和 asyncio 混用会有问题

【本项目的定时任务列表】
- 热榜同步：每1小时抓取一次所有平台热榜
- 热榜向量化：每1小时对新增热榜做向量化（跟随热榜同步后执行）
- 过期数据清理：每天凌晨2点清理7天前的旧数据
"""

import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from app.config import settings
from app.utils.logger import logger


# 全局调度器单例（整个应用共享一个）
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """获取调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            # 时区设置（影响 CronTrigger 的执行时间）
            timezone="Asia/Shanghai",
            # 调度器自身的日志级别
            job_defaults={
                "coalesce": True,       # 如果任务积压（如服务器暂停后重启），合并为一次执行
                "max_instances": 1,     # 同一个任务最多同时运行1个实例（防止重叠）
                "misfire_grace_time": 300,  # 错过执行时间后，5分钟内仍可补跑
            }
        )
    return _scheduler


# ====================================================
# 定时任务函数
# ====================================================

async def job_sync_hotlist():
    """
    定时任务：同步所有平台热榜
    
    执行频率：每 HOTLIST_SYNC_INTERVAL 秒（默认1小时）
    执行逻辑：
    1. 抓取5个平台热榜数据
    2. 写入 hotlist_sync 数据库表
    3. 触发向量化（把新数据存入 ChromaDB）
    """
    logger.info(f"[定时任务] 热榜同步开始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        from app.services.hotlist_service import sync_all_hotlists
        stats = await sync_all_hotlists()

        # 同步完成后，触发向量化
        total_new = sum(stats.values())
        if total_new > 0:
            logger.info(f"[定时任务] 新增 {total_new} 条热榜，开始向量化...")
            await job_embed_new_hotlist()

        logger.info(f"[定时任务] 热榜同步完成: {stats}")

    except Exception as e:
        logger.error(f"[定时任务] 热榜同步失败: {e}")


async def job_embed_new_hotlist():
    """
    定时任务：对 pending 状态的热榜做向量化

    通常由 job_sync_hotlist 调用，也可以单独触发（手动修复用）
    
    执行逻辑：
    1. 查询 embedding_status='pending' 的热榜记录
    2. 批量调用 DeepSeek Embedding API
    3. 存入 ChromaDB
    4. 更新数据库记录状态为 'completed'
    """
    logger.info("[定时任务] 开始对新热榜做向量化...")

    from app.database import SessionLocal
    from app.models.hotlist_sync import HotlistSync
    from app.services.embedding_service import upsert_hotlist_to_chroma

    db = SessionLocal()
    try:
        # 查询未向量化的记录（最多处理100条，防止单次耗时太长）
        pending_items = (
            db.query(HotlistSync)
            .filter(
                HotlistSync.embedding_status == "pending",
                HotlistSync.is_expired == 0,
            )
            .limit(100)
            .all()
        )

        if not pending_items:
            logger.info("[定时任务] 没有待向量化的热榜数据")
            return

        logger.info(f"[定时任务] 待向量化: {len(pending_items)} 条")

        # 转为 dict 列表供 embedding_service 使用
        items_dict = [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "source_platform": item.source_platform,
                "rank": item.rank,
                "hot_value": item.hot_value,
            }
            for item in pending_items
        ]

        # 执行向量化（可能耗时较长，DeepSeek API 调用）
        count = upsert_hotlist_to_chroma(items_dict)

        # 更新状态
        ids = [item.id for item in pending_items]
        db.query(HotlistSync).filter(HotlistSync.id.in_(ids)).update(
            {"embedding_status": "completed"},
            synchronize_session=False
        )
        db.commit()

        logger.info(f"[定时任务] 向量化完成: {count} 条")

    except Exception as e:
        db.rollback()
        logger.error(f"[定时任务] 向量化失败: {e}")
    finally:
        db.close()


async def job_cleanup_expired_data():
    """
    定时任务：清理过期热榜数据
    
    执行频率：每天凌晨 2:00
    清理规则：
    - 删除 7 天前的过期热榜记录（is_expired=1 且 fetched_at 超过7天）
    - 同步删除 ChromaDB 中对应的向量
    
    为什么不立即删？
    保留7天是为了：
    1. 历史数据分析（哪些话题最火？）
    2. 防止误删（某些任务可能引用了旧热榜 ID）
    """
    logger.info("[定时任务] 开始清理过期热榜数据...")

    from app.database import SessionLocal
    from app.models.hotlist_sync import HotlistSync
    from app.services.embedding_service import delete_hotlist_vectors

    db = SessionLocal()
    try:
        # 查找7天前的过期记录
        cleanup_before = datetime.utcnow() - timedelta(days=7)
        expired_items = (
            db.query(HotlistSync)
            .filter(
                HotlistSync.is_expired == 1,
                HotlistSync.fetched_at < cleanup_before,
            )
            .all()
        )

        if not expired_items:
            logger.info("[定时任务] 没有需要清理的过期数据")
            return

        expired_ids = [item.id for item in expired_items]

        # 先删 ChromaDB 向量
        delete_hotlist_vectors(expired_ids)

        # 再删数据库记录
        db.query(HotlistSync).filter(HotlistSync.id.in_(expired_ids)).delete(
            synchronize_session=False
        )
        db.commit()

        logger.info(f"[定时任务] 清理完成，删除了 {len(expired_ids)} 条过期记录")

    except Exception as e:
        db.rollback()
        logger.error(f"[定时任务] 清理失败: {e}")
    finally:
        db.close()


# ====================================================
# 调度器事件监听（用于日志记录）
# ====================================================

def _on_job_executed(event):
    """任务执行成功的回调"""
    logger.debug(f"[调度器] 任务 '{event.job_id}' 执行成功")


def _on_job_error(event):
    """任务执行失败的回调"""
    logger.error(f"[调度器] 任务 '{event.job_id}' 执行出错: {event.exception}")


# ====================================================
# 调度器启动/停止（在 main.py lifespan 中调用）
# ====================================================

def start_scheduler():
    """
    启动调度器，注册所有定时任务
    在 FastAPI 应用启动时调用
    """
    scheduler = get_scheduler()

    # 注册事件监听器
    scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)

    # ---- 注册任务 ----

    # 任务1：热榜同步（每 HOTLIST_SYNC_INTERVAL 秒执行一次）
    scheduler.add_job(
        func=job_sync_hotlist,
        trigger=IntervalTrigger(seconds=settings.HOTLIST_SYNC_INTERVAL),
        id="sync_hotlist",
        name="热榜同步",
        replace_existing=True,  # 重启时替换已存在的同名任务
    )

    # 任务2：每天凌晨2点清理过期数据
    scheduler.add_job(
        func=job_cleanup_expired_data,
        trigger=CronTrigger(hour=2, minute=0),
        id="cleanup_expired",
        name="过期数据清理",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        f"[调度器] 启动成功，共 {len(scheduler.get_jobs())} 个任务\n"
        f"  - 热榜同步：每 {settings.HOTLIST_SYNC_INTERVAL // 60} 分钟\n"
        f"  - 过期清理：每天 02:00"
    )

    # 启动后立即执行一次热榜同步（不用等第一个间隔）
    # run_date=None 等价于"尽快执行"
    scheduler.add_job(
        func=job_sync_hotlist,
        trigger="date",  # 一次性任务
        id="sync_hotlist_startup",
        name="启动时热榜同步",
        misfire_grace_time=60,
    )
    logger.info("[调度器] 已安排启动时立即执行一次热榜同步")


def stop_scheduler():
    """
    停止调度器
    在 FastAPI 应用关闭时调用，确保正在运行的任务能完成
    """
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=True)  # wait=True：等待正在执行的任务完成再停止
        logger.info("[调度器] 已安全停止")
