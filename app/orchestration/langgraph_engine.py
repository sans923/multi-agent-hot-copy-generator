"""
LangGraph 编排引擎（第二个实现）
================================
- ORCHESTRATION_MODE=fixed   → copy_pipeline_graph（三节点固定流水线）
- ORCHESTRATION_MODE=agentic → agentic_pipeline_graph（分级 + 规划 + 按步执行）
- ORCHESTRATION_MODE=lead    → lead_pipeline_graph（Lead 总控单节点图）
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Callable
from uuid import uuid4

from langgraph.types import Command
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.orchestration.base import OrchestrationEngine
from app.models.task import Task, TaskStatus
from app.services.task_lifecycle_service import set_task_execution_status
from app.agents.pipeline_state import (
    build_awaiting_human_result,
    build_failure_result,
    build_success_result,
    init_pipeline_state,
)
from app.services.langgraph_checkpoint import ParameterizedSqliteSaver
from app.services.orchestration_persistence import (
    apply_result_meta_to_task,
    build_orchestration_meta,
    mark_task_processing,
)
from app.services.orchestration_policy import resolve_execution_mode


class LangGraphOrchestrationEngine(OrchestrationEngine):
    """
    LangGraph 文案主流程编排引擎。

    使用方法（一般由工厂创建）：
        engine = LangGraphOrchestrationEngine()
        result = engine.run(db=db, task_id=123)
    """

    name = "langgraph"

    def __init__(
        self,
        *,
        checkpointer=None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self._owns_checkpointer = checkpointer is None
        self.checkpointer = checkpointer
        self.session_factory = session_factory
        self._agentic_graph = None

    def close(self) -> None:
        close = getattr(self.checkpointer, "close", None)
        if self._owns_checkpointer and close:
            close()
        self.checkpointer = None

    def _get_checkpointer(self):
        if self.checkpointer is None:
            self.checkpointer = ParameterizedSqliteSaver(
                Path(settings.LANGGRAPH_CHECKPOINT_PATH)
            )
        return self.checkpointer

    def _get_agentic_graph(self):
        if self._agentic_graph is None:
            from app.lang.graph.agentic_pipeline_graph import (
                build_durable_agentic_pipeline_graph,
            )

            self._agentic_graph = build_durable_agentic_pipeline_graph(
                checkpointer=self._get_checkpointer(),
                session_factory=self.session_factory,
            )
        return self._agentic_graph

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _interrupts(snapshot) -> list[dict]:
        values: list[dict] = []
        for task in snapshot.tasks:
            values.extend(interrupt.value for interrupt in task.interrupts)
        return values

    def _ensure_thread(self, db: Session, task: Task) -> str:
        meta = dict(task.orchestration_meta or {})
        thread_id = meta.get("thread_id")
        if not thread_id:
            thread_id = f"task-{task.id}-{uuid4()}"
            meta.update({
                "thread_id": thread_id,
                "durability_mode": "langgraph_sqlite_v1",
                "graph_version": "agentic_v1",
            })
            meta.pop("checkpoint", None)
            task.orchestration_meta = meta
            db.commit()
        return str(thread_id)

    def _project_snapshot(self, db: Session, task_id: int, snapshot) -> dict:
        state = dict(snapshot.values)
        interrupts = self._interrupts(snapshot)
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"success": False, "task_id": task_id, "error": "任务不存在"}

        durable_meta = {
            key: value
            for key, value in dict(task.orchestration_meta or {}).items()
            if key in {
                "thread_id", "durability_mode", "graph_version", "execution_mode",
                "resolved_mode", "durable_effects",
            }
        }
        if interrupts:
            state["awaiting_human"] = True
            payload = interrupts[0]
            state["error"] = payload.get("reason") or state.get("error")
            meta = build_orchestration_meta(state)
            meta.update(durable_meta)
            meta["interrupt"] = payload
            meta.pop("checkpoint", None)
            task.orchestration_meta = meta
            set_task_execution_status(task, TaskStatus.AWAITING_HUMAN, reason=state.get("error") or "需人工介入")
            task.error_message = (state.get("error") or "需人工介入")[:500]
            db.commit()
            return build_awaiting_human_result(state)

        result = state.get("result")
        if not result:
            result = build_failure_result(state) if state.get("abort") else build_success_result(state)
        apply_result_meta_to_task(db, task_id, result, state)
        db.refresh(task)
        meta = dict(task.orchestration_meta or {})
        meta.update(durable_meta)
        meta.pop("checkpoint", None)
        meta.pop("interrupt", None)
        task.orchestration_meta = meta
        db.commit()
        return result

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
            return self.start(db=db, task_id=task_id)

        from app.lang.graph.copy_pipeline_graph import run_copy_pipeline

        return run_copy_pipeline(db=db, task_id=task_id)

    def start(self, db: Session, task_id: int, *, thread_id: str | None = None) -> dict:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"success": False, "task_id": task_id, "error": "任务不存在"}
        stored_thread_id = self._ensure_thread(db, task)
        if thread_id is not None and thread_id != stored_thread_id:
            raise ValueError("thread_id 与任务绑定不一致")
        state, early_error = init_pipeline_state(db, task_id)
        if early_error:
            return early_error
        assert state is not None
        state.pop("db", None)
        state.pop("result", None)
        mark_task_processing(db, task_id)
        self._get_agentic_graph().invoke(
            state,
            config=self._config(stored_thread_id),
        )
        snapshot = self._get_agentic_graph().get_state(self._config(stored_thread_id))
        return self._project_snapshot(db, task_id, snapshot)

    def resume(
        self,
        db: Session,
        task_id: int,
        *,
        thread_id: str,
        human_input: dict,
    ) -> dict:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"success": False, "task_id": task_id, "error": "任务不存在"}
        meta = dict(task.orchestration_meta or {})
        if meta.get("durability_mode") != "langgraph_sqlite_v1":
            raise ValueError("任务不是 durable LangGraph 线程")
        if meta.get("thread_id") != thread_id:
            raise ValueError("thread_id 与任务绑定不一致")
        snapshot = self._get_agentic_graph().get_state(self._config(thread_id))
        if not self._interrupts(snapshot):
            raise ValueError("线程当前没有待处理 interrupt")
        updated = (
            db.query(Task)
            .filter(Task.id == task_id, Task.status == TaskStatus.AWAITING_HUMAN)
            .update(
                {
                    Task.status: TaskStatus.PROCESSING,
                    Task.execution_status: "running",
                    Task.status_updated_at: datetime.utcnow(),
                    Task.error_message: None,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            db.rollback()
            return {
                "success": False,
                "task_id": task_id,
                "resume_conflict": True,
                "error": "恢复请求已被其他执行器接管",
            }
        db.commit()
        try:
            self._get_agentic_graph().invoke(
                Command(resume=human_input),
                config=self._config(thread_id),
            )
        except Exception as exc:
            db.rollback()
            failure_snapshot = self._get_agentic_graph().get_state(self._config(thread_id))
            if not self._interrupts(failure_snapshot) and failure_snapshot.next:
                try:
                    # Command 已消费旧 interrupt 后，失败节点可能尚未产生新 interrupt。
                    # 继续同一 checkpoint；execute 节点会根据 running effect 停止重放，
                    # 并确定性路由到新的 human_gate。
                    self._get_agentic_graph().invoke(
                        None,
                        config=self._config(thread_id),
                    )
                    failure_snapshot = self._get_agentic_graph().get_state(
                        self._config(thread_id)
                    )
                except Exception:
                    failure_snapshot = self._get_agentic_graph().get_state(
                        self._config(thread_id)
                    )
            if self._interrupts(failure_snapshot):
                return self._project_snapshot(db, task_id, failure_snapshot)
            (
                db.query(Task)
                .filter(Task.id == task_id, Task.status == TaskStatus.PROCESSING)
                .update(
                    {
                        Task.status: TaskStatus.FAILED,
                        Task.execution_status: "failed",
                        Task.status_updated_at: datetime.utcnow(),
                        Task.error_message: f"恢复执行失败: {exc}"[:500],
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            return build_failure_result({
                "task_id": task_id,
                "abort": True,
                "error": f"恢复执行失败: {exc}",
            })
        resumed_snapshot = self._get_agentic_graph().get_state(self._config(thread_id))
        return self._project_snapshot(db, task_id, resumed_snapshot)

    def get_state(self, *, thread_id: str) -> dict:
        snapshot = self._get_agentic_graph().get_state(self._config(thread_id))
        return {
            "thread_id": thread_id,
            "values": dict(snapshot.values),
            "next": list(snapshot.next),
            "interrupts": self._interrupts(snapshot),
            "created_at": snapshot.created_at,
            "config": snapshot.config,
        }
