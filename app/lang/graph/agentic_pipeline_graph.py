"""
LangGraph：Agentic 增强流水线
==============================
任务分级 → 规划 → 按步执行 → 失败路由 → 收尾

图结构：
    START
      ↓
    classify
      ↓ (条件边)
    simple_pipeline ──→ END        （委托 fixed 三阶段）
      ↓ complex
    create_plan
      ↓
    execute_step ←──┐
      ↓             │ (retry / 步进)
    handle_outcome ─┘
      ↓ (条件边)
    finalize / mark_failed ──→ END
"""

from __future__ import annotations

import time
from typing import Callable, Literal

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from sqlalchemy.orm import Session

from app.agents.agentic_runners import (
    audit_awaiting_human,
    handle_step_outcome,
    plan_has_more_steps,
    run_classify_stage,
    run_execute_current_step,
    run_plan_stage,
)
from app.agents.pipeline_runners import PipelineAgents, run_full_pipeline
from app.agents.pipeline_state import (
    PipelineState,
    build_awaiting_human_result,
    build_failure_result,
    build_success_result,
    init_pipeline_state,
    is_step_limit_reached,
    is_timed_out,
)
from app.services.orchestration_persistence import (
    apply_result_meta_to_task,
    mark_task_processing,
)
from app.services.orchestration_policy import decide_final_quality_gate
from app.services.audit_service import write_audit_log
from app.config import settings
from app.database import SessionLocal
from app.models.task import TaskStatus
from app.utils.logger import logger


_agents: PipelineAgents | None = None
_agentic_pipeline_graph = None


def _get_agents() -> PipelineAgents:
    global _agents
    if _agents is None:
        _agents = PipelineAgents()
    return _agents


def _classify_node(state: PipelineState) -> dict:
    return run_classify_stage(state)


def _plan_node(state: PipelineState) -> dict:
    return run_plan_stage(state)


def _execute_step_node(state: PipelineState) -> dict:
    if is_timed_out(state):
        return {
            "awaiting_human": True,
            "failure_level": "human",
            "error": f"任务超时（>{settings.AGENT_TIMEOUT_SEC}s）",
        }
    if is_step_limit_reached(state):
        return {
            "awaiting_human": True,
            "failure_level": "human",
            "error": f"超过最大步数 {state.get('max_steps')}",
        }
    db = state["db"]
    return run_execute_current_step(db, _get_agents(), state)


def _handle_outcome_node(state: PipelineState) -> dict:
    return handle_step_outcome(state)


def _simple_pipeline_node(state: PipelineState) -> dict:
    """简单任务：直接跑 fixed 流水线，结果写入 state.result。"""
    db = state["db"]
    task_id = state["task_id"]
    result = run_full_pipeline(db, task_id, agents=_get_agents())
    result["task_mode"] = "simple"
    apply_result_meta_to_task(db, task_id, result, state)
    return {"result": result, "task_mode": "simple"}


def _finalize_node(state: PipelineState) -> dict:
    result = build_success_result(state)
    apply_result_meta_to_task(state["db"], state["task_id"], result, state)
    logger.info(
        f"Agentic 图完成: task_id={state.get('task_id')}, "
        f"mode={state.get('task_mode')}, final_copy_id={result.get('final_copy_id')}"
    )
    return {"result": result}


def _quality_gate_node(state: PipelineState) -> dict:
    """确定性终稿门控：模型负责评分，规则负责是否放行。"""
    decision = decide_final_quality_gate(state)
    gate = decision.as_dict()
    entry = {"type": "quality_gate", **gate}
    write_audit_log(
        state.get("db"),
        state.get("task_id"),
        "quality_gate",
        "final_quality_gate",
        output_summary=gate,
        status="success" if decision.passed else "failed",
        failure_level=None if decision.passed else "local",
    )
    updates = {
        "quality_gate": gate,
        "decision_log": [*(state.get("decision_log") or []), entry],
    }
    if decision.action == "awaiting_human":
        updates.update({
            "awaiting_human": True,
            "failure_level": "human",
            "error": f"质量门控未通过：{', '.join(decision.failed_checks)}",
        })
    return updates


def _prepare_quality_rewrite_node(state: PipelineState) -> dict:
    """门控失败后仅回退 Reviewer 一次，形成有上限的恢复闭环。"""
    steps = (state.get("plan") or {}).get("steps") or []
    reviewer_idx = next(
        (i for i, step in enumerate(steps) if step.get("stage") == "reviewer"),
        None,
    )
    if reviewer_idx is None:
        return {
            "awaiting_human": True,
            "failure_level": "human",
            "error": "质量门控要求重写，但计划中没有 Reviewer 步骤",
        }
    return {
        "current_step": reviewer_idx,
        "rewrite_count": 1,
        "awaiting_human": False,
        "failure_level": "local",
        "decision_log": [
            *(state.get("decision_log") or []),
            {
                "type": "quality_rewrite",
                "to_stage": "reviewer",
                "round": 1,
                "reason": "failed_sections_detected",
            },
        ],
    }


def _mark_awaiting_human_node(state: PipelineState) -> dict:
    result = build_awaiting_human_result(state)
    db = state["db"]
    task_id = state["task_id"]
    from app.services.orchestration_persistence import mark_task_awaiting_human

    audit_awaiting_human(state)
    mark_task_awaiting_human(db, task_id, state)
    return {"result": result}


def _mark_failed_node(state: PipelineState) -> dict:
    result = build_failure_result(state)
    apply_result_meta_to_task(state["db"], state["task_id"], result, state)
    logger.error(
        f"Agentic 图失败: task_id={state.get('task_id')}, error={result.get('error')}"
    )
    return {"result": result}


def _route_after_classify(
    state: PipelineState,
) -> Literal["simple_pipeline", "plan"]:
    if state.get("execution_mode") != "plan" and state.get("task_mode") == "simple":
        return "simple_pipeline"
    return "plan"


def _route_after_handle(
    state: PipelineState,
) -> Literal["execute_step", "quality_gate", "mark_failed", "awaiting_human"]:
    if state.get("awaiting_human"):
        return "awaiting_human"
    if state.get("abort"):
        return "mark_failed"
    if plan_has_more_steps(state):
        return "execute_step"
    return "quality_gate"


def _route_after_quality_gate(
    state: PipelineState,
) -> Literal["finalize", "prepare_quality_rewrite", "awaiting_human"]:
    if state.get("awaiting_human"):
        return "awaiting_human"
    action = (state.get("quality_gate") or {}).get("action")
    if action == "rewrite":
        return "prepare_quality_rewrite"
    return "finalize"


def build_agentic_pipeline_graph():
    """构建并编译 Agentic StateGraph。"""
    graph = StateGraph(PipelineState)

    graph.add_node("classify", _classify_node)
    graph.add_node("simple_pipeline", _simple_pipeline_node)
    graph.add_node("create_plan", _plan_node)
    graph.add_node("execute_step", _execute_step_node)
    graph.add_node("handle_outcome", _handle_outcome_node)
    graph.add_node("evaluate_quality", _quality_gate_node)
    graph.add_node("prepare_quality_rewrite", _prepare_quality_rewrite_node)
    graph.add_node("finalize", _finalize_node)
    graph.add_node("mark_failed", _mark_failed_node)
    graph.add_node("persist_awaiting_human", _mark_awaiting_human_node)

    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "simple_pipeline": "simple_pipeline",
            "plan": "create_plan",
        },
    )
    graph.add_edge("simple_pipeline", END)
    graph.add_edge("create_plan", "execute_step")
    graph.add_edge("execute_step", "handle_outcome")
    graph.add_conditional_edges(
        "handle_outcome",
        _route_after_handle,
        {
            "execute_step": "execute_step",
            "quality_gate": "evaluate_quality",
            "mark_failed": "mark_failed",
            "awaiting_human": "persist_awaiting_human",
        },
    )
    graph.add_conditional_edges(
        "evaluate_quality",
        _route_after_quality_gate,
        {
            "finalize": "finalize",
            "prepare_quality_rewrite": "prepare_quality_rewrite",
            "awaiting_human": "persist_awaiting_human",
        },
    )
    graph.add_edge("prepare_quality_rewrite", "execute_step")
    graph.add_edge("finalize", END)
    graph.add_edge("mark_failed", END)
    graph.add_edge("persist_awaiting_human", END)

    return graph.compile()


def build_durable_agentic_pipeline_graph(
    *,
    checkpointer,
    session_factory: Callable[[], Session] = SessionLocal,
):
    """构建不持有 Session、支持 interrupt/Command resume 的 durable 图。"""

    def with_session(state: PipelineState, operation):
        db = session_factory()
        try:
            runtime_state: PipelineState = dict(state)
            runtime_state["db"] = db
            return operation(db, runtime_state)
        finally:
            db.close()

    def classify_node(state: PipelineState) -> dict:
        return with_session(state, lambda _db, runtime: run_classify_stage(runtime))

    def plan_node(state: PipelineState) -> dict:
        return with_session(state, lambda _db, runtime: run_plan_stage(runtime))

    def execute_node(state: PipelineState) -> dict:
        if is_timed_out(state):
            return {
                "awaiting_human": True,
                "failure_level": "human",
                "error": f"任务超时（>{settings.AGENT_TIMEOUT_SEC}s）",
            }
        if is_step_limit_reached(state):
            return {
                "awaiting_human": True,
                "failure_level": "human",
                "error": f"超过最大步数 {state.get('max_steps')}",
            }
        def execute_once(db: Session, runtime: PipelineState) -> dict:
            from app.models.task import Task

            operation_key = ":".join(str(runtime.get(key, 0) or 0) for key in (
                "current_step", "resume_count", "retry_count", "reflect_count",
                "rewrite_count", "step_count",
            ))
            task = db.query(Task).filter(Task.id == runtime["task_id"]).first()
            if not task:
                return {"abort": True, "error": "任务不存在"}
            meta = dict(task.orchestration_meta or {})
            effects = dict(meta.get("durable_effects") or {})
            existing = effects.get(operation_key) or {}
            if existing.get("status") == "completed":
                return dict(existing.get("result") or {})
            if existing.get("status") == "running":
                return {
                    "awaiting_human": True,
                    "failure_level": "human",
                    "error": "上次节点执行结果不确定，已停止自动重放以避免重复调用",
                }
            effects[operation_key] = {"status": "running"}
            meta["durable_effects"] = effects
            task.orchestration_meta = meta
            db.commit()

            result = run_execute_current_step(db, _get_agents(), runtime)
            db.refresh(task)
            latest_meta = dict(task.orchestration_meta or {})
            latest_effects = dict(latest_meta.get("durable_effects") or {})
            latest_effects[operation_key] = {"status": "completed", "result": result}
            latest_meta["durable_effects"] = latest_effects
            task.orchestration_meta = latest_meta
            db.commit()
            return result

        return with_session(state, execute_once)

    def handle_node(state: PipelineState) -> dict:
        return with_session(state, lambda _db, runtime: handle_step_outcome(runtime))

    def quality_node(state: PipelineState) -> dict:
        return with_session(state, lambda _db, runtime: _quality_gate_node(runtime))

    def simple_node(state: PipelineState) -> dict:
        return with_session(state, lambda _db, runtime: _simple_pipeline_node(runtime))

    def finalize_node(state: PipelineState) -> dict:
        return with_session(state, lambda _db, runtime: _finalize_node(runtime))

    def failed_node(state: PipelineState) -> dict:
        return with_session(state, lambda _db, runtime: _mark_failed_node(runtime))

    def human_gate(state: PipelineState) -> dict:
        decision = interrupt({
            "kind": "agentic_human_intervention",
            "task_id": state.get("task_id"),
            "reason": state.get("error") or "需人工介入",
            "allowed_actions": ["retry", "accept_draft", "cancel"],
            "current_step": state.get("current_step"),
        })
        action = decision.get("action") if isinstance(decision, dict) else None
        if action not in {"retry", "accept_draft", "cancel"}:
            return {
                "awaiting_human": True,
                "failure_level": "human",
                "error": "无效的人工操作",
                "human_action": None,
            }
        updates = {
            "human_action": action,
            "awaiting_human": False,
            "failure_level": None,
            "error": None,
            "deadline_ts": time.time() + settings.AGENT_TIMEOUT_SEC,
            "resume_count": (state.get("resume_count") or 0) + 1,
        }
        if action == "retry":
            updates.update({"retry_count": 0, "step_count": 0})
            if (state.get("quality_gate") or {}).get("action") == "awaiting_human":
                steps = (state.get("plan") or {}).get("steps") or []
                reviewer_idx = next(
                    (index for index, step in enumerate(steps) if step.get("stage") == "reviewer"),
                    None,
                )
                if reviewer_idx is not None:
                    updates.update({
                        "current_step": reviewer_idx,
                        "rewrite_count": 0,
                        "quality_gate": {},
                    })
        return updates

    def route_human(state: PipelineState) -> str:
        return state.get("human_action") or "human_gate"

    def accept_node(state: PipelineState) -> dict:
        from app.agents.pipeline_runners import promote_draft_to_final
        from app.services.orchestration_persistence import apply_result_meta_to_task

        def accept(db: Session, runtime: PipelineState) -> dict:
            copy_id = promote_draft_to_final(
                db,
                runtime.get("copy_id"),
                task_id=int(runtime["task_id"]),
            )
            if copy_id is None:
                return {
                    "awaiting_human": True,
                    "failure_level": "human",
                    "error": "找不到属于当前任务的有效初稿，无法接受",
                    "human_action": None,
                }
            result = build_success_result({**runtime, "final_copy_id": copy_id})
            apply_result_meta_to_task(db, int(runtime["task_id"]), result, runtime)
            return {"final_copy_id": copy_id, "result": result}

        return with_session(state, accept)

    def cancel_node(state: PipelineState) -> dict:
        def cancel(db: Session, runtime: PipelineState) -> dict:
            from app.models.task import Task

            task = db.query(Task).filter(Task.id == runtime["task_id"]).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = "用户取消任务"
                db.commit()
            return {
                "abort": True,
                "error": "用户取消任务",
                "result": build_failure_result({**runtime, "error": "用户取消任务"}),
            }

        return with_session(state, cancel)

    graph = StateGraph(PipelineState)
    graph.add_node("classify", classify_node)
    graph.add_node("simple_pipeline", simple_node)
    graph.add_node("create_plan", plan_node)
    graph.add_node("execute_step", execute_node)
    graph.add_node("handle_outcome", handle_node)
    graph.add_node("evaluate_quality", quality_node)
    graph.add_node("prepare_quality_rewrite", _prepare_quality_rewrite_node)
    graph.add_node("human_gate", human_gate)
    graph.add_node("accept_draft", accept_node)
    graph.add_node("cancel", cancel_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("mark_failed", failed_node)
    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {"simple_pipeline": "simple_pipeline", "plan": "create_plan"},
    )
    graph.add_edge("simple_pipeline", END)
    graph.add_edge("create_plan", "execute_step")
    graph.add_edge("execute_step", "handle_outcome")
    graph.add_conditional_edges(
        "handle_outcome",
        _route_after_handle,
        {
            "execute_step": "execute_step",
            "quality_gate": "evaluate_quality",
            "mark_failed": "mark_failed",
            "awaiting_human": "human_gate",
        },
    )
    graph.add_conditional_edges(
        "evaluate_quality",
        _route_after_quality_gate,
        {
            "finalize": "finalize",
            "prepare_quality_rewrite": "prepare_quality_rewrite",
            "awaiting_human": "human_gate",
        },
    )
    graph.add_conditional_edges(
        "human_gate",
        route_human,
        {
            "retry": "execute_step",
            "accept_draft": "accept_draft",
            "cancel": "cancel",
            "human_gate": "human_gate",
        },
    )
    graph.add_edge("prepare_quality_rewrite", "execute_step")
    graph.add_conditional_edges(
        "accept_draft",
        lambda state: "human_gate" if state.get("awaiting_human") else "end",
        {"human_gate": "human_gate", "end": END},
    )
    graph.add_edge("cancel", END)
    graph.add_edge("finalize", END)
    graph.add_edge("mark_failed", END)
    return graph.compile(checkpointer=checkpointer)


def run_agentic_pipeline_graph(db, task_id: int) -> dict:
    """Agentic 图对外入口。"""
    global _agentic_pipeline_graph

    state, early_error = init_pipeline_state(db, task_id)
    if early_error:
        return early_error
    assert state is not None

    mark_task_processing(db, task_id)
    write_audit_log(
        db,
        task_id,
        "orchestration",
        "agentic_start",
        input_summary={"mode": "langgraph"},
    )

    logger.info(f"{'=' * 50}")
    logger.info(f"LangGraph Agentic 流程开始: task_id={task_id}")
    logger.info(f"{'=' * 50}")

    if _agentic_pipeline_graph is None:
        _agentic_pipeline_graph = build_agentic_pipeline_graph()

    final_state = _agentic_pipeline_graph.invoke(state)
    result = final_state.get("result")
    if result:
        return result

    if final_state.get("abort"):
        return build_failure_result(final_state)
    return build_success_result(final_state)
