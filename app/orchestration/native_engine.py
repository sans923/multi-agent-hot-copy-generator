"""
Native 编排引擎（第一个实现）
==============================
把现有自研编排器 AgentOrchestrator 适配为统一接口 OrchestrationEngine 的第一个实现。

【设计要点：零行为变更】
本类是一个「薄适配器（Adapter）」：
- 不复制、不修改 AgentOrchestrator 的任何逻辑；
- run() 直接转发给 AgentOrchestrator().run(db, task_id)，原样返回其 dict。
因此当 settings.ORCHESTRATION_ENGINE == "native"（默认）时，
系统行为与重构前完全一致（逐字段一致），可随时回滚。

【为什么在 run() 内部惰性实例化 AgentOrchestrator？】
沿用 tasks.py 原有的惰性 import 习惯，避免模块加载期触发
三个 Agent 的初始化（它们会构造 SkillRegistry 等），把副作用收敛到真正执行时。
"""

from sqlalchemy.orm import Session

from app.orchestration.base import OrchestrationEngine


class NativeOrchestrationEngine(OrchestrationEngine):
    """
    自研顺序流水线编排引擎（适配 AgentOrchestrator）。

    使用方法（一般由工厂创建，不直接 new）：
        engine = NativeOrchestrationEngine()
        result = engine.run(db=db, task_id=123)
    """

    name = "native"

    def run(self, db: Session, task_id: int) -> dict:
        """
        转发给自研 AgentOrchestrator，原样返回其结果。

        参数：
            db: 数据库会话
            task_id: 任务ID
        返回：
            dict（与 AgentOrchestrator.run 完全一致）
        """
        # 惰性 import，避免模块加载期初始化三个 Agent / SkillRegistry
        from app.agents.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        return orchestrator.run(db=db, task_id=task_id)
