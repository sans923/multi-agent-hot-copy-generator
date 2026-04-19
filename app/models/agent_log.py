"""
Agent 执行日志表（agent_logs）
==============================
记录每个 Agent 每次执行的详细过程
这是整个多智能体系统的"黑匣子"，用于：
1. 调试：Agent 为什么做出某个决策？
2. 监控：哪个 Agent 最慢？哪个 Skill 调用最多？
3. 简历/面试展示：可以展示系统的执行轨迹，证明架构的真实性

Agent 执行流程（典型一次）：
  需求理解Agent -> 调用 parse_requirement Skill
               -> 调用 search_hotlist Skill
               -> 返回解析结果
  每次 Skill 调用 = 一条 agent_log 记录
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="日志ID")

    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联任务ID"
    )

    # 哪个 Agent 在执行
    agent_name = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Agent名称（requirement/copywriter/reviewer）"
    )

    # 哪个 Skill 被调用（Function Calling 的函数名）
    skill_name = Column(
        String(50),
        nullable=True,
        comment="调用的Skill名称（如 search_hotlist）"
    )

    # Skill 调用的输入参数（JSON格式）
    skill_input = Column(JSON, nullable=True, comment="Skill调用的输入参数")

    # Skill 执行的输出结果
    skill_output = Column(JSON, nullable=True, comment="Skill执行的输出结果")

    # 执行状态：success / failed / timeout
    status = Column(
        String(20),
        nullable=False,
        default="success",
        comment="执行状态"
    )

    # 错误信息（失败时）
    error_message = Column(Text, nullable=True, comment="错误信息")

    # 执行耗时（秒）：用于性能分析
    duration_seconds = Column(Float, nullable=True, comment="执行耗时(秒)")

    # 消耗的 Token 数
    tokens_used = Column(Integer, default=0, comment="本次调用消耗的Token数")

    # Agent 给大模型发的 prompt（调试用）
    prompt_snapshot = Column(Text, nullable=True, comment="本次调用的完整prompt快照")

    # 大模型返回的原始响应
    raw_response = Column(Text, nullable=True, comment="大模型原始响应")

    # 迭代轮次（审核Agent最多1次迭代）
    iteration = Column(Integer, default=1, comment="Agent迭代轮次")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True, comment="执行时间")

    task = relationship("Task", back_populates="agent_logs")

    def __repr__(self) -> str:
        return f"<AgentLog id={self.id} agent={self.agent_name} skill={self.skill_name} status={self.status}>"
