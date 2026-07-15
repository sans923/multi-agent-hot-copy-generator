"""
LangGraph 编排引擎（第二个实现）
================================
- ORCHESTRATION_MODE=fixed   → copy_pipeline_graph（三节点固定流水线）
- ORCHESTRATION_MODE=agentic → agentic_pipeline_graph（分级 + 规划 + 按步执行）
- ORCHESTRATION_MODE=lead    → lead_pipeline_graph（Lead 总控单节点图）
"""

from sqlalchemy.orm import Session

from app.config import settings
from app.orchestration.base import OrchestrationEngine
from app.models.task import Task
from app.services.orchestration_policy import resolve_execution_mode


class LangGraphOrchestrationEngine(OrchestrationEngine):
    """
    LangGraph 文案主流程编排引擎。

    使用方法（一般由工厂创建）：
        engine = LangGraphOrchestrationEngine()
        result = engine.run(db=db, task_id=123)
    """

    name = "langgraph"

    def run(self, db: Session, task_id: int) -> dict:
        task = db.query(Task).filter(Task.id == task_id).first()
        meta = task.orchestration_meta if task and isinstance(task.orchestration_meta, dict) else {}
        requested_mode = meta.get("execution_mode")
        mode = (
            resolve_execution_mode(requested_mode)
            if requested_mode
            else (settings.ORCHESTRATION_MODE or "fixed").strip().lower()
        )
        if mode == "lead":
            from app.lang.graph.lead_pipeline_graph import run_lead_pipeline_graph

            return run_lead_pipeline_graph(db=db, task_id=task_id)

        if mode == "agentic":
            from app.lang.graph.agentic_pipeline_graph import run_agentic_pipeline_graph

            return run_agentic_pipeline_graph(db=db, task_id=task_id)

        from app.lang.graph.copy_pipeline_graph import run_copy_pipeline

        return run_copy_pipeline(db=db, task_id=task_id)
