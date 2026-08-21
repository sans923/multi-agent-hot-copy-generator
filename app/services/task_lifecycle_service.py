"""任务三域状态的统一写入规则。"""

from __future__ import annotations

from datetime import datetime

from app.models.task import Task, TaskStatus


_EXECUTION_STATUS_BY_LEGACY = {
    TaskStatus.PENDING: "queued",
    TaskStatus.PROCESSING: "running",
    TaskStatus.AWAITING_HUMAN: "waiting_human",
    TaskStatus.COMPLETED: "succeeded",
    TaskStatus.FAILED: "failed",
}
_REASON_UNSET = object()


def set_task_execution_status(
    task: Task,
    legacy_status: TaskStatus | str,
    *,
    reason: str | None | object = _REASON_UNSET,
) -> None:
    """同时维护兼容 status 与新的执行状态轴，不负责提交事务。"""
    normalized = (
        legacy_status
        if isinstance(legacy_status, TaskStatus)
        else TaskStatus(str(legacy_status))
    )
    task.status = normalized
    task.execution_status = _EXECUTION_STATUS_BY_LEGACY[normalized]
    task.status_updated_at = datetime.utcnow()
    if reason is not _REASON_UNSET:
        task.status_reason = str(reason)[:500] if reason else None
