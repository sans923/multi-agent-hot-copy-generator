"""
编排审计日志服务
================
统一写入 orchestration_audit_logs，供全链路追溯。
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy.orm import Session

from app.utils.logger import logger


def _next_sequence_no(db: Session, task_id: int) -> int:
    from sqlalchemy import func

    from app.models.orchestration_audit_log import OrchestrationAuditLog

    current = (
        db.query(func.max(OrchestrationAuditLog.sequence_no))
        .filter(OrchestrationAuditLog.task_id == task_id)
        .scalar()
    )
    return int(current or 0) + 1


def write_audit_log(
    db: Session | None,
    task_id: int | None,
    step_type: str,
    step_name: str,
    *,
    agent_name: str | None = None,
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    status: str = "success",
    failure_level: str | None = None,
    duration_ms: float | None = None,
    error_message: str | None = None,
) -> None:
    """
    写入一条编排审计日志（失败不影响主业务）。
    """
    if not db or not task_id:
        return

    try:
        from app.models.orchestration_audit_log import OrchestrationAuditLog

        log = OrchestrationAuditLog(
            task_id=task_id,
            step_type=step_type,
            step_name=step_name,
            agent_name=agent_name,
            sequence_no=_next_sequence_no(db, task_id),
            input_summary=input_summary,
            output_summary=output_summary,
            status=status,
            failure_level=failure_level,
            duration_ms=round(duration_ms, 2) if duration_ms is not None else None,
            error_message=(error_message[:2000] if error_message else None),
        )
        db.add(log)
        db.commit()
    except Exception as exc:
        logger.error(f"写入审计日志失败（不影响主业务）: {exc}")
        try:
            db.rollback()
        except Exception:
            pass


@contextmanager
def audit_step(
    db: Session | None,
    task_id: int | None,
    step_type: str,
    step_name: str,
    *,
    agent_name: str | None = None,
    input_summary: dict[str, Any] | None = None,
    failure_level: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """
    上下文管理器：自动记录步骤耗时与成功/失败。

    用法：
        with audit_step(db, task_id, "stage", "requirement") as out:
            ...
            out["result"] = "ok"
    """
    start = time.time()
    output: dict[str, Any] = {}
    error: str | None = None
    status = "success"

    try:
        yield output
    except Exception as exc:
        status = "failed"
        error = str(exc)
        raise
    finally:
        duration_ms = (time.time() - start) * 1000
        write_audit_log(
            db,
            task_id,
            step_type,
            step_name,
            agent_name=agent_name,
            input_summary=input_summary,
            output_summary=output if output else None,
            status=status,
            failure_level=failure_level,
            duration_ms=duration_ms,
            error_message=error,
        )
