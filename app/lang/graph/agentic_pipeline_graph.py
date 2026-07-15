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
    plan
      ↓
    execute_step ←──┐
      ↓             │ (retry / 步进)
    handle_outcome ─┘
      ↓ (条件边)
    finalize / mark_failed ──→ END
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, StateGraph

from app.agents.agentic_runners import (
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
from app.services.orchestration_persistence import apply_result_meta_to_task
from app.services.orchestration_policy import decide_final_quality_gate
from app.services.audit_service import write_audit_log
from app.config import settings
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
    graph.add_node("plan", _plan_node)
    graph.add_node("execute_step", _execute_step_node)
    graph.add_node("handle_outcome", _handle_outcome_node)
    graph.add_node("quality_gate", _quality_gate_node)
    graph.add_node("prepare_quality_rewrite", _prepare_quality_rewrite_node)
    graph.add_node("finalize", _finalize_node)
    graph.add_node("mark_failed", _mark_failed_node)
    graph.add_node("awaiting_human", _mark_awaiting_human_node)

    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "simple_pipeline": "simple_pipeline",
            "plan": "plan",
        },
    )
    graph.add_edge("simple_pipeline", END)
    graph.add_edge("plan", "execute_step")
    graph.add_edge("execute_step", "handle_outcome")
    graph.add_conditional_edges(
        "handle_outcome",
        _route_after_handle,
        {
            "execute_step": "execute_step",
            "quality_gate": "quality_gate",
            "mark_failed": "mark_failed",
            "awaiting_human": "awaiting_human",
        },
    )
    graph.add_conditional_edges(
        "quality_gate",
        _route_after_quality_gate,
        {
            "finalize": "finalize",
            "prepare_quality_rewrite": "prepare_quality_rewrite",
            "awaiting_human": "awaiting_human",
        },
    )
    graph.add_edge("prepare_quality_rewrite", "execute_step")
    graph.add_edge("finalize", END)
    graph.add_edge("mark_failed", END)
    graph.add_edge("awaiting_human", END)

    return graph.compile()


def run_agentic_pipeline_graph(db, task_id: int) -> dict:
    """Agentic 图对外入口。"""
    global _agentic_pipeline_graph

    state, early_error = init_pipeline_state(db, task_id)
    if early_error:
        return early_error
    assert state is not None

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
