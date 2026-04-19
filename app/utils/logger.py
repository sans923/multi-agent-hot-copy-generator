"""
统一日志模块
============
作用：配置全局日志，所有模块通过 from app.utils.logger import logger 使用

为什么用 loguru 而不是 Python 自带 logging？
- 更简洁：一行配置代替十几行
- 自动轮转：日志文件超过 10MB 自动切割，保留最近 7 天
- 颜色高亮：终端输出彩色日志，DEBUG/INFO/ERROR 一眼区分
- 异常追踪：自动捕获完整堆栈信息

使用方法：
    from app.utils.logger import logger
    logger.info("服务启动成功")
    logger.error("发生错误: {}", error_msg)
    logger.debug("调试信息")
"""

import sys
from pathlib import Path
from loguru import logger

from app.config import settings


def setup_logger() -> None:
    """
    配置日志输出
    这个函数在 main.py 启动时调用一次
    """
    # 先清除 loguru 的默认配置（默认只输出到 stderr）
    logger.remove()

    # ---- 终端输出（开发时好用）----
    # format 是日志格式，{time}时间 {level}级别 {name}模块名 {message}内容
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        level=settings.LOG_LEVEL,
        colorize=True,  # 终端彩色输出
    )

    # ---- 文件输出（生产环境排查问题用）----
    log_path = Path(settings.LOG_FILE_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)  # 自动创建 logs 目录

    logger.add(
        str(log_path),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
        level=settings.LOG_LEVEL,
        rotation="10 MB",      # 超过 10MB 自动切割成新文件
        retention="7 days",    # 只保留最近 7 天的日志
        compression="zip",     # 旧日志压缩节省空间
        encoding="utf-8",
    )

    logger.info(f"日志系统初始化完成，日志级别: {settings.LOG_LEVEL}")


# 直接导出 logger 对象，其他模块 from app.utils.logger import logger 即可
__all__ = ["logger", "setup_logger"]
