"""
系统日志写入工具
================
提供一个简单的函数，在业务代码里一行写入 system_logs 表

【为什么封装成工具函数而不是直接写表？】
1. 统一格式：所有日志都走同一个入口，字段格式一致
2. 容错处理：写日志失败不能影响主业务（用 try/except 保护）
3. 方便扩展：以后接入 Elasticsearch 只改这一个地方

使用示例：
    from app.utils.log_writer import write_log
    
    write_log(
        db=db,
        category="auth",
        action="user.login",
        message=f"用户 {user.username} 登录成功",
        user_id=user.id,
        level="INFO",
    )
"""

from datetime import datetime
from typing import Optional, Any
from sqlalchemy.orm import Session

from app.utils.logger import logger


def write_log(
    db: Session,
    category: str,
    action: str,
    message: str,
    level: str = "INFO",
    user_id: Optional[int] = None,
    task_id: Optional[int] = None,
    extra: Optional[dict] = None,
    ip_address: Optional[str] = None,
    duration_ms: Optional[int] = None,
    is_success: bool = True,
) -> None:
    """
    写入系统日志（容错版本：写入失败不抛出异常）
    
    参数：
        db: 数据库会话
        category: 日志分类，建议值：
                  "auth"     - 用户认证相关
                  "task"     - 任务生命周期
                  "agent"    - Agent执行事件
                  "hotlist"  - 热榜同步
                  "system"   - 系统事件
        action: 操作标识，格式 "对象.动作"，如 "user.login" / "task.create"
        message: 人类可读的日志描述
        level: "INFO" / "WARNING" / "ERROR"
        user_id: 操作用户ID（无用户操作传 None）
        task_id: 关联任务ID（无关联传 None）
        extra: 附加信息字典
        ip_address: 客户端IP
        duration_ms: 操作耗时（毫秒）
        is_success: 操作是否成功
    """
    try:
        from app.models.system_log import SystemLog
        log = SystemLog(
            level=level,
            category=category,
            action=action,
            message=message,
            user_id=user_id,
            task_id=task_id,
            extra=extra,
            ip_address=ip_address,
            duration_ms=duration_ms,
            is_success=1 if is_success else 0,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        # 写日志失败不能影响主业务！只记录到文件日志
        logger.error(f"写入 system_logs 失败（不影响主业务）: {e}")
