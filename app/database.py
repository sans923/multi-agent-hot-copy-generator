"""
数据库连接模块
==============
作用：创建数据库引擎（Engine）和会话工厂（SessionLocal），
      提供给整个应用使用

核心概念解释：
- Engine（引擎）：数据库连接池，负责和数据库底层通信
- Session（会话）：一次数据库"事务对话"，类比一次对话窗口
  - 在会话中可以增删改查
  - 会话结束后要关闭，释放连接
- Base：所有 ORM 模型的父类，SQLAlchemy 通过它知道有哪些表

工作流程：
    1. 应用启动 -> 创建 Engine（建立连接池）
    2. 每次 API 请求 -> 从连接池取一个 Session
    3. 操作数据库 -> 提交事务 or 回滚
    4. 请求结束 -> Session 关闭，连接还回连接池
"""

from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.config import settings
from app.utils.logger import logger


# ====================================================
# 数据库引擎配置
# ====================================================

def _get_engine_kwargs() -> dict:
    """
    根据数据库类型返回不同的引擎参数
    
    SQLite 和 MySQL 的连接参数不一样：
    - SQLite 是文件型数据库，不支持连接池的 pool_size 参数
    - MySQL 需要连接池来复用连接，提高性能
    """
    if settings.DATABASE_URL.startswith("sqlite"):
        # SQLite 特殊配置
        return {
            "connect_args": {"check_same_thread": False},
            "echo": settings.DEBUG,
        }
    if settings.DATABASE_URL.startswith("mysql"):
        # MySQL 连接池（pool_recycle 避免 MySQL 8h 断连）
        return {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "echo": settings.DEBUG,
        }
    # PostgreSQL 等
    return {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "echo": settings.DEBUG,
    }


def _prepare_sqlite_dir() -> None:
    """如果是 SQLite，确保数据目录存在"""
    if settings.DATABASE_URL.startswith("sqlite:///"):
        # 从 "sqlite:///./data/app.db" 中提取 "./data/app.db"
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


_prepare_sqlite_dir()

engine = create_engine(
    settings.DATABASE_URL,
    **_get_engine_kwargs()
)


# SQLite 额外优化：启用外键约束（SQLite 默认关闭外键检查，需手动开启）
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ====================================================
# 会话工厂
# ====================================================

# SessionLocal 是一个"工厂类"，每次调用 SessionLocal() 生成一个新的数据库会话
# autocommit=False：不自动提交，需要手动调用 session.commit()
# autoflush=False：不自动刷新，避免意外的中间状态写入数据库
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# ====================================================
# ORM 模型基类
# ====================================================

# 所有数据库模型（表）都要继承这个 Base
# SQLAlchemy 通过它追踪所有定义的表，用于 create_all() 建表
Base = declarative_base()


# ====================================================
# 依赖注入函数（供 FastAPI 使用）
# ====================================================

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 依赖注入函数，用 yield 实现"请求级别"的数据库会话管理
    
    工作原理（yield 的魔法）：
    1. 请求进来 -> 执行 yield 之前的代码（创建 session）
    2. yield db -> 把 session 传给 API 函数使用
    3. 请求结束（无论成功还是报错）-> 执行 finally 中的代码（关闭 session）
    
    这确保数据库连接一定会被释放，不会造成连接泄漏
    
    使用方法（在 API 路由函数中）：
        @router.get("/users")
        def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db: Session = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"数据库会话异常，回滚事务: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def create_tables(bind=None) -> None:
    """
    创建所有数据库表（开发时使用）
    
    注意：这里必须先 import 所有模型，否则 Base.metadata 不知道有哪些表
    顺序很重要：被外键引用的表要先建（users 先于 tasks）
    """
    from app.models import user, task, task_execution_job, document, copy, agent_log, hotlist_sync, toutiao_reference, orchestration_audit_log, system_log, memory_index_job, memory, knowledge  # noqa: F401

    logger.info("开始创建数据库表...")
    Base.metadata.create_all(bind=bind or engine)
    logger.info("数据库表创建完成")
