"""
系统日志表（system_logs）
==========================
记录系统级别的操作日志，和 agent_logs 的区别：

agent_logs：Agent 每次调用 Skill 的微观记录（谁调了什么函数，参数是什么）
system_logs：业务操作的宏观记录（谁做了什么事，比如用户登录/任务创建/热榜同步）

【system_logs 的三类用途】
1. 安全审计：谁在什么时候登录/注册/修改了什么
2. 任务追踪：任务从创建到完成的生命周期事件
3. 系统监控：热榜同步/向量化等定时任务的执行情况

【对应的 3 个查询接口】
GET /api/v1/logs/agent   - 查 Agent Skill 调用记录（调试Agent用）
GET /api/v1/logs/tasks   - 查任务执行汇总（了解整体状态）
GET /api/v1/logs/system  - 查系统操作日志（安全审计/运维用）
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Index

from app.database import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 日志级别：INFO / WARNING / ERROR
    level = Column(
        String(10),
        nullable=False,
        default="INFO",
        index=True,
        comment="日志级别"
    )

    # 日志分类：auth / task / hotlist / agent / system
    category = Column(
        String(30),
        nullable=False,
        index=True,
        comment="日志分类（auth/task/hotlist/agent/system）"
    )

    # 操作类型（如 user.register / task.create / hotlist.sync）
    action = Column(
        String(100),
        nullable=False,
        index=True,
        comment="操作类型"
    )

    # 操作描述（人类可读的摘要）
    message = Column(Text, nullable=False, comment="日志消息")

    # 关联用户（可为空，系统操作没有用户）
    user_id = Column(Integer, nullable=True, index=True, comment="操作用户ID")

    # 关联任务（可为空）
    task_id = Column(Integer, nullable=True, index=True, comment="关联任务ID")

    # 额外数据（JSON格式，存任意附加信息）
    extra = Column(JSON, nullable=True, comment="附加数据")

    # 客户端 IP（安全审计用）
    ip_address = Column(String(45), nullable=True, comment="客户端IP")

    # 执行耗时（毫秒）
    duration_ms = Column(Integer, nullable=True, comment="操作耗时(毫秒)")

    # 是否成功
    is_success = Column(Integer, default=1, nullable=False, comment="是否成功(1=是,0=否)")

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="记录时间"
    )

    # 联合索引：按分类+时间查询是最常见的模式
    __table_args__ = (
        Index("ix_system_logs_category_created", "category", "created_at"),
        Index("ix_system_logs_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SystemLog id={self.id} level={self.level} category={self.category} action={self.action}>"
