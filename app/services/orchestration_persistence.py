"""
编排状态持久化
==============
将 Agentic 流水线 checkpoint / 元数据写入 Task.orchestration_meta，支持人工介入后恢复。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.pipeline_state import PipelineState
from app.models.task import Task, TaskStatus
from app.utils.logger import logger

# PipelineState 中不可 JSON 序列化的字段
_NON_SERIALIZABLE_KEYS = frozenset({"db", "result"})


def state_to_checkpoint(state: PipelineState) -> dict[str, Any]:
    """将 PipelineState 转为可持久化的 checkpoint（去除 db）。"""
    checkpoint: dict[str, Any] = {}
    for key, value in state.items():
        if key in _NON_SERIALIZABLE_KEYS:
            continue
        checkpoint[key] = value
    return checkpoint


def checkpoint_to_state(
    checkpoint: dict[str, Any],
    db: Session,
    task_id: int,
) -> PipelineState:
    """从 checkpoint 恢复 PipelineState，注入 db 与 task_id。"""
    state: PipelineState = dict(checkpoint)  # type: ignore[assignment]
    state["db"] = db
    state["task_id"] = task_id
    state["awaiting_human"] = False
    state["failure_level"] = None
    return state


def build_orchestration_meta(state: PipelineState) -> dict[str, Any]:
    """从 state 提取对外展示的 orchestration 元数据。"""
    plan = state.get("plan") or {}
    return {
        "execution_mode": state.get("execution_mode", "fast"),
        "resolved_mode": state.get("resolved_mode", "fixed"),
        "selected_style_card_id": state.get("selected_style_card_id"),
        "task_mode": state.get("task_mode"),
        "plan_source": plan.get("source"),
        "plan_reasoning": plan.get("reasoning"),
        "plan_steps": [
            {
                "step_id": s.get("step_id"),
                "stage": s.get("stage"),
                "description": s.get("description"),
                "can_skip": bool(s.get("can_skip", False)),
            }
            for s in (plan.get("steps") or [])
        ],
        "current_step": state.get("current_step"),
        "step_count": state.get("step_count"),
        "failure_level": state.get("failure_level"),
        "classify_reasons": state.get("classify_reasons") or [],
        "verification": state.get("verification"),
        "awaiting_human": state.get("awaiting_human", False),
        "human_prompt": state.get("error"),
        "quality_gate": state.get("quality_gate") or {},
        "decision_log": state.get("decision_log") or [],
        "skipped_steps": state.get("skipped_steps") or [],
    }


def save_orchestration_meta(
    db: Session,
    task_id: int,
    state: PipelineState,
    *,
    save_checkpoint: bool = False,
) -> None:
    """写入 Task.orchestration_meta；可选同时保存 checkpoint。"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return

    meta = build_orchestration_meta(state)
    if save_checkpoint:
        meta["checkpoint"] = state_to_checkpoint(state)

    task.orchestration_meta = meta
    db.commit()
    logger.debug(f"编排元数据已保存: task_id={task_id}, awaiting_human={meta.get('awaiting_human')}")


def load_checkpoint(db: Session, task_id: int) -> dict[str, Any] | None:
    """从 Task.orchestration_meta 读取 checkpoint。"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or not task.orchestration_meta:
        return None
    meta = task.orchestration_meta
    if isinstance(meta, dict):
        return meta.get("checkpoint")
    return None


def mark_task_processing(db: Session, task_id: int) -> None:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task and task.status == TaskStatus.PENDING:
        task.status = TaskStatus.PROCESSING
        db.commit()


def mark_task_awaiting_human(db: Session, task_id: int, state: PipelineState) -> None:
    """标记任务等待人工介入，并保存 checkpoint。"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return
    task.status = TaskStatus.AWAITING_HUMAN
    task.error_message = (state.get("error") or "需人工介入")[:500]
    save_orchestration_meta(db, task_id, state, save_checkpoint=True)


def mark_task_completed_from_meta(
    db: Session,
    task_id: int,
    state: PipelineState,
) -> None:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return
    task.status = TaskStatus.COMPLETED
    task.error_message = None
    save_orchestration_meta(db, task_id, state, save_checkpoint=False)


def apply_result_meta_to_task(
    db: Session,
    task_id: int,
    result: dict[str, Any],
    state: PipelineState | None = None,
) -> None:
    """根据流水线结果更新 Task 状态与 orchestration_meta。"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return

    if state:
        meta = build_orchestration_meta(state)
        existing = task.orchestration_meta if isinstance(task.orchestration_meta, dict) else {}
        if result.get("awaiting_human"):
            meta["checkpoint"] = existing.get("checkpoint") or state_to_checkpoint(state)
        task.orchestration_meta = meta
    elif result.get("task_mode"):
        existing = dict(task.orchestration_meta or {})
        existing.update({
            "task_mode": result.get("task_mode"),
            "plan_source": result.get("plan_source"),
            "failure_level": result.get("failure_level"),
        })
        task.orchestration_meta = existing

    if result.get("awaiting_human"):
        task.status = TaskStatus.AWAITING_HUMAN
        task.error_message = (result.get("error") or "需人工介入")[:500]
    elif result.get("success"):
        task.status = TaskStatus.COMPLETED
        task.error_message = None
    elif not result.get("success"):
        task.status = TaskStatus.FAILED
        task.error_message = (result.get("error") or "任务失败")[:500]

    db.commit()
