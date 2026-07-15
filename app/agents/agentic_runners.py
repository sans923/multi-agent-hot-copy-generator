"""
Agentic 流水线执行器
====================
任务分级 → 规划 → 按步执行 → 规则/Judge 验证 → 失败分级 → 人工介入 checkpoint。
"""

from __future__ import annotations

import time
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.agents.pipeline_runners import (
    PipelineAgents,
    promote_draft_to_final,
    run_copywriter_stage,
    run_full_pipeline,
    run_requirement_stage,
    run_reviewer_stage,
)
from app.agents.pipeline_state import (
    PipelineState,
    build_awaiting_human_result,
    build_failure_result,
    build_success_result,
    init_pipeline_state,
    is_step_limit_reached,
    is_timed_out,
)
from app.config import settings
from app.models.task import Task, TaskStatus
from app.services.orchestration_persistence import (
    apply_result_meta_to_task,
    checkpoint_to_state,
    load_checkpoint,
    mark_task_awaiting_human,
    mark_task_processing,
    save_orchestration_meta,
)
from app.services.audit_service import write_audit_log
from app.services.planner_service import generate_plan
from app.services.task_classifier import classify_task
from app.services.reflect_service import reflect_on_step_failure
from app.services.orchestration_policy import decide_final_quality_gate, decide_step_skip
from app.services.verify_service import verify_step
from app.utils.logger import logger

ResumeAction = Literal["retry", "accept_draft", "cancel"]


def _merge_state(state: PipelineState, updates: dict[str, Any]) -> PipelineState:
    merged: PipelineState = dict(state)
    merged.update(updates)
    return merged


def run_classify_stage(state: PipelineState) -> dict[str, Any]:
    """节点：任务分级。"""
    result = classify_task(
        raw_requirement=state.get("raw_requirement", ""),
        platform=state.get("platform", "weibo"),
    )
    logger.info(
        f"任务分级: task_id={state.get('task_id')}, "
        f"mode={result['task_mode']}, reasons={result.get('reasons')}"
    )
    write_audit_log(
        state.get("db"),
        state.get("task_id"),
        "orchestration",
        "classify_task",
        input_summary={"platform": state.get("platform")},
        output_summary={
            "task_mode": result["task_mode"],
            "reasons": result.get("reasons"),
        },
    )
    return {
        "task_mode": result["task_mode"],
        "classify_reasons": result.get("reasons") or [],
    }


def run_plan_stage(state: PipelineState) -> dict[str, Any]:
    """节点：生成执行计划（simple 用默认计划，complex 调 Planner）。"""
    plan = generate_plan(
        raw_requirement=state.get("raw_requirement", ""),
        platform=state.get("platform", "weibo"),
        task_mode=state.get("task_mode") or "simple",
        classify_reasons=state.get("classify_reasons") or [],
    )
    write_audit_log(
        state.get("db"),
        state.get("task_id"),
        "orchestration",
        "generate_plan",
        output_summary={
            "source": plan.get("source"),
            "step_count": len(plan.get("steps") or []),
            "reasoning": (plan.get("reasoning") or "")[:200],
        },
    )
    return {
        "plan": plan,
        "current_step": 0,
        "step_count": 0,
        "retry_count": 0,
    }


def _get_current_step_def(state: PipelineState) -> dict[str, Any] | None:
    plan = state.get("plan") or {}
    steps = plan.get("steps") or []
    idx = state.get("current_step") or 0
    if 0 <= idx < len(steps):
        return steps[idx]
    return None


def run_execute_current_step(
    db: Session,
    agents: PipelineAgents,
    state: PipelineState,
) -> dict[str, Any]:
    """执行 plan[current_step] 对应的 stage。"""
    step_def = _get_current_step_def(state)
    if not step_def:
        return {"last_step_failed": False}

    stage = (step_def.get("stage") or "").lower()
    step_id = step_def.get("step_id") or stage
    skip = decide_step_skip(state, step_def)
    if skip.should_skip:
        decision = {
            "type": "skip",
            "step_id": step_id,
            "stage": stage,
            "reason": skip.reason,
        }
        write_audit_log(
            db,
            state.get("task_id"),
            "orchestration",
            "step_skipped",
            input_summary={"step_id": step_id, "stage": stage},
            output_summary={"reason": skip.reason},
            status="success",
        )
        return {
            "step_count": (state.get("step_count") or 0) + 1,
            "last_step_failed": False,
            "decision_log": [*(state.get("decision_log") or []), decision],
            "skipped_steps": [*(state.get("skipped_steps") or []), decision],
        }

    _audit_execute_step(db, state, step_def)
    logger.info(
        f"执行计划步骤: task_id={state.get('task_id')}, "
        f"step={step_id}, stage={stage}, idx={state.get('current_step')}"
    )

    updates: dict[str, Any] = {
        "step_count": (state.get("step_count") or 0) + 1,
        "last_step_failed": False,
    }

    if stage == "requirement":
        updates.update(run_requirement_stage(db, agents, state))
    elif stage == "copywriter":
        updates.update(run_copywriter_stage(db, agents, state))
    elif stage == "reviewer":
        updates.update(run_reviewer_stage(db, agents, state))
    elif stage == "verify":
        verification = verify_step(state, "verify")
        updates["verification"] = verification
        updates["last_step_failed"] = not verification.get("passed", True)
        stages = dict(state.get("stages") or {})
        stages["verify"] = verification
        updates["stages"] = stages
        write_audit_log(
            db,
            state.get("task_id"),
            "verify",
            step_id,
            input_summary={"stage": stage},
            output_summary={
                "passed": verification.get("passed"),
                "source": verification.get("source"),
                "failed_checks": verification.get("failed_checks"),
            },
            status="success" if verification.get("passed") else "failed",
        )
    else:
        updates["error"] = f"未知 stage: {stage}"
        updates["last_step_failed"] = True

    if updates.get("abort"):
        updates["last_step_failed"] = True

    return updates


def handle_step_outcome(state: PipelineState) -> dict[str, Any]:
    """
    处理单步结果：成功则步进；失败则 L1 重试 / L2 局部 / L4 人工介入。
    """
    if state.get("abort"):
        return {"failure_level": "global", "error": state.get("error")}

    if not state.get("last_step_failed"):
        return {
            "current_step": (state.get("current_step") or 0) + 1,
            "retry_count": 0,
        }

    retry_count = (state.get("retry_count") or 0) + 1
    if retry_count <= settings.MAX_RETRY_PER_STEP:
        logger.warning(
            f"L1 重试: task_id={state.get('task_id')}, "
            f"step={state.get('current_step')}, retry={retry_count}"
        )
        write_audit_log(
            state.get("db"),
            state.get("task_id"),
            "orchestration",
            "step_retry",
            input_summary={"step": state.get("current_step"), "retry": retry_count},
            status="retry",
            failure_level="retry",
        )
        return {
            "retry_count": retry_count,
            "failure_level": "retry",
            "last_step_failed": False,
            "decision_log": [
                *(state.get("decision_log") or []),
                {
                    "type": "retry",
                    "step": state.get("current_step"),
                    "retry": retry_count,
                    "reason": "step_verification_failed",
                },
            ],
        }

    step_def = _get_current_step_def(state) or {}
    stage = (step_def.get("stage") or "").lower()

    if stage in ("verify", "copywriter", "reviewer"):
        reflect_count = (state.get("reflect_count") or 0) + 1
        if reflect_count <= settings.MAX_REFLECT_ROUNDS:
            reflection = reflect_on_step_failure(state, stage=stage)
            logger.warning(
                f"L2 Reflexion: 回退 copywriter, reflect={reflect_count}, "
                f"source={reflection.get('source')}"
            )
            plan = state.get("plan") or {}
            steps = plan.get("steps") or []
            copywriter_idx = next(
                (i for i, s in enumerate(steps) if s.get("stage") == "copywriter"),
                None,
            )
            if copywriter_idx is not None:
                notes = list(state.get("reflect_notes") or [])
                notes.append(reflection.get("summary") or "")
                ctx = list(state.get("context_messages") or [])
                if reflection.get("context_append"):
                    ctx.append({
                        "role": "system",
                        "content": reflection["context_append"],
                    })
                write_audit_log(
                    state.get("db"),
                    state.get("task_id"),
                    "orchestration",
                    "reflect_node",
                    input_summary={"stage": stage, "reflect_count": reflect_count},
                    output_summary={
                        "summary": reflection.get("summary"),
                        "rewrite_hint": reflection.get("rewrite_hint"),
                        "focus": reflection.get("focus"),
                        "source": reflection.get("source"),
                    },
                    status="retry",
                    failure_level="local",
                )
                return {
                    "current_step": copywriter_idx,
                    "retry_count": 0,
                    "reflect_count": reflect_count,
                    "reflect_notes": notes,
                    "rewrite_hint": reflection.get("rewrite_hint") or "",
                    "context_messages": ctx,
                    "failure_level": "local",
                    "last_step_failed": False,
                    "decision_log": [
                        *(state.get("decision_log") or []),
                        {
                            "type": "reflect",
                            "from_stage": stage,
                            "to_stage": "copywriter",
                            "round": reflect_count,
                            "reason": reflection.get("summary") or "local_recovery",
                        },
                    ],
                }

    return {
        "failure_level": "human",
        "awaiting_human": True,
        "error": state.get("error") or "步骤多次失败，需人工介入",
        "decision_log": [
            *(state.get("decision_log") or []),
            {
                "type": "escalate",
                "step": state.get("current_step"),
                "reason": "bounded_recovery_exhausted",
            },
        ],
    }


def _audit_awaiting_human(state: PipelineState) -> None:
    write_audit_log(
        state.get("db"),
        state.get("task_id"),
        "human",
        "awaiting_human",
        output_summary={"error": state.get("error")},
        status="failed",
        failure_level="human",
        error_message=state.get("error"),
    )


def _audit_execute_step(
    db: Session,
    state: PipelineState,
    step_def: dict[str, Any],
) -> None:
    write_audit_log(
        db,
        state.get("task_id"),
        "orchestration",
        "execute_plan_step",
        input_summary={
            "step_id": step_def.get("step_id"),
            "stage": step_def.get("stage"),
            "index": state.get("current_step"),
        },
    )


def plan_has_more_steps(state: PipelineState) -> bool:
    plan = state.get("plan") or {}
    steps = plan.get("steps") or []
    return (state.get("current_step") or 0) < len(steps)


def _run_complex_loop(
    db: Session,
    agents: PipelineAgents,
    state: PipelineState,
) -> PipelineState:
    """complex 任务主循环。"""
    while plan_has_more_steps(state):
        if is_timed_out(state):
            state = _merge_state(state, {
                "awaiting_human": True,
                "failure_level": "human",
                "error": f"任务超时（>{settings.AGENT_TIMEOUT_SEC}s）",
            })
            break

        if is_step_limit_reached(state):
            state = _merge_state(state, {
                "awaiting_human": True,
                "failure_level": "human",
                "error": f"超过最大步数 {state.get('max_steps')}",
            })
            break

        state = _merge_state(state, run_execute_current_step(db, agents, state))

        if state.get("abort"):
            break

        state = _merge_state(state, handle_step_outcome(state))

        if state.get("awaiting_human"):
            break

    return state


def _run_bounded_quality_gate(
    db: Session,
    agents: PipelineAgents,
    state: PipelineState,
) -> PipelineState:
    """为非 LangGraph/人工恢复路径补齐同一套终稿门控与一次重写。"""
    while True:
        decision = decide_final_quality_gate(state)
        gate = decision.as_dict()
        state = _merge_state(state, {
            "quality_gate": gate,
            "decision_log": [
                *(state.get("decision_log") or []),
                {"type": "quality_gate", **gate},
            ],
        })
        write_audit_log(
            db,
            state.get("task_id"),
            "quality_gate",
            "final_quality_gate",
            output_summary=gate,
            status="success" if decision.passed else "failed",
            failure_level=None if decision.passed else "local",
        )
        if decision.action == "finalize":
            return state
        if decision.action == "awaiting_human":
            return _merge_state(state, {
                "awaiting_human": True,
                "failure_level": "human",
                "error": f"质量门控未通过：{', '.join(decision.failed_checks)}",
            })

        steps = (state.get("plan") or {}).get("steps") or []
        reviewer_idx = next(
            (i for i, step in enumerate(steps) if step.get("stage") == "reviewer"),
            None,
        )
        if reviewer_idx is None:
            return _merge_state(state, {
                "awaiting_human": True,
                "failure_level": "human",
                "error": "质量门控要求重写，但计划中没有 Reviewer 步骤",
            })
        state = _merge_state(state, {
            "current_step": reviewer_idx,
            "rewrite_count": 1,
            "decision_log": [
                *(state.get("decision_log") or []),
                {
                    "type": "quality_rewrite",
                    "to_stage": "reviewer",
                    "round": 1,
                    "reason": "failed_sections_detected",
                },
            ],
        })
        state = _run_complex_loop(db, agents, state)
        if state.get("awaiting_human") or state.get("abort"):
            return state


def run_agentic_pipeline(
    db: Session,
    task_id: int,
    agents: PipelineAgents | None = None,
) -> dict[str, Any]:
    """
    Agentic 编排入口（native 与 LangGraph 共用逻辑）。

    - simple：直接 run_full_pipeline（与 fixed 完全一致）
    - complex：Plan → 逐步 Execute → Verify → 失败分级 / 人工暂停
    """
    agents = agents or PipelineAgents()
    mark_task_processing(db, task_id)

    logger.info(f"{'=' * 50}")
    logger.info(f"Agentic 编排开始: task_id={task_id}")
    logger.info(f"{'=' * 50}")

    write_audit_log(
        db, task_id, "orchestration", "agentic_start",
        input_summary={"mode": "agentic"},
    )

    state, early_error = init_pipeline_state(db, task_id)
    if early_error:
        return early_error
    assert state is not None

    state = _merge_state(state, run_classify_stage(state))

    if state.get("execution_mode") != "plan" and state.get("task_mode") == "simple":
        logger.info(f"简单任务，委托 fixed 流水线: task_id={task_id}")
        result = run_full_pipeline(db, task_id, agents=agents)
        result["task_mode"] = "simple"
        apply_result_meta_to_task(db, task_id, result, state)
        return result

    state = _merge_state(state, run_plan_stage(state))
    state = _run_complex_loop(db, agents, state)
    if not state.get("awaiting_human") and not state.get("abort"):
        state = _run_bounded_quality_gate(db, agents, state)

    if state.get("awaiting_human"):
        _audit_awaiting_human(state)
        mark_task_awaiting_human(db, task_id, state)
        result = build_awaiting_human_result(state)
        apply_result_meta_to_task(db, task_id, result, state)
        return result

    if state.get("abort"):
        result = build_failure_result(state)
        apply_result_meta_to_task(db, task_id, result, state)
        return result

    logger.info(
        f"Agentic 编排完成: task_id={task_id}, mode=complex, "
        f"steps_executed={state.get('step_count')}"
    )
    result = build_success_result(state)
    apply_result_meta_to_task(db, task_id, result, state)
    return result


def resume_agentic_pipeline(
    db: Session,
    task_id: int,
    action: ResumeAction,
    agents: PipelineAgents | None = None,
) -> dict[str, Any]:
    """
    人工介入后恢复任务。

    action:
        retry        — 从 checkpoint 继续执行
        accept_draft — 接受当前初稿为终稿
        cancel       — 取消任务
    """
    agents = agents or PipelineAgents()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"success": False, "error": f"任务 {task_id} 不存在", "task_id": task_id}

    if task.status != TaskStatus.AWAITING_HUMAN:
        return {
            "success": False,
            "error": f"任务状态为 {task.status.value}，非 awaiting_human",
            "task_id": task_id,
        }

    if action == "cancel":
        write_audit_log(db, task_id, "human", "resume_cancel", status="failed")
        task.status = TaskStatus.FAILED
        task.error_message = "用户取消任务"
        db.commit()
        return {
            "success": False,
            "error": "用户取消任务",
            "task_id": task_id,
        }

    if action == "accept_draft":
        write_audit_log(db, task_id, "human", "resume_accept_draft")
        checkpoint = load_checkpoint(db, task_id)
        copy_id = checkpoint.get("copy_id") if checkpoint else None
        final_copy_id = promote_draft_to_final(db, copy_id)
        task.status = TaskStatus.COMPLETED
        task.error_message = None
        meta = dict(task.orchestration_meta or {})
        meta["awaiting_human"] = False
        meta["failure_level"] = None
        meta["human_action"] = "accept_draft"
        task.orchestration_meta = meta
        db.commit()
        return {
            "success": True,
            "task_id": task_id,
            "final_copy_id": final_copy_id,
            "message": "已接受初稿为终稿",
        }

    # action == retry
    write_audit_log(db, task_id, "human", "resume_retry")
    checkpoint = load_checkpoint(db, task_id)
    if not checkpoint:
        return {
            "success": False,
            "error": "找不到 checkpoint，无法恢复",
            "task_id": task_id,
        }

    task.status = TaskStatus.PROCESSING
    task.error_message = None
    db.commit()

    state = checkpoint_to_state(checkpoint, db, task_id)
    state["retry_count"] = 0
    state["step_count"] = 0
    state["deadline_ts"] = time.time() + settings.AGENT_TIMEOUT_SEC

    previous_gate = state.get("quality_gate") or {}
    if previous_gate.get("action") == "awaiting_human":
        steps = (state.get("plan") or {}).get("steps") or []
        reviewer_idx = next(
            (i for i, step in enumerate(steps) if step.get("stage") == "reviewer"),
            None,
        )
        if reviewer_idx is not None:
            state["current_step"] = reviewer_idx
            state["rewrite_count"] = 0
            state["quality_gate"] = {}
            state["decision_log"] = [
                *(state.get("decision_log") or []),
                {
                    "type": "human_retry",
                    "to_stage": "reviewer",
                    "reason": "user_started_new_bounded_recovery_round",
                },
            ]

    state = _run_complex_loop(db, agents, state)
    if not state.get("awaiting_human") and not state.get("abort"):
        state = _run_bounded_quality_gate(db, agents, state)

    if state.get("awaiting_human"):
        _audit_awaiting_human(state)
        mark_task_awaiting_human(db, task_id, state)
        result = build_awaiting_human_result(state)
        apply_result_meta_to_task(db, task_id, result, state)
        return result

    if state.get("abort"):
        result = build_failure_result(state)
        apply_result_meta_to_task(db, task_id, result, state)
        return result

    result = build_success_result(state)
    apply_result_meta_to_task(db, task_id, result, state)
    return result
