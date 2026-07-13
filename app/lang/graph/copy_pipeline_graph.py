"""
LangGraph：文案生成【主流程图】
================================
三 Agent 顺序编排 + 文案创作失败条件分支，与 native 流水线行为对齐。

图结构：
    START
      ↓
    requirement
      ↓
    copywriter
      ↓ (条件边)
    reviewer ──→ finalize ──→ END
      ↑
    mark_failed ──→ END  （copywriter 失败时）
"""

from typing import Literal

from langgraph.graph import END, StateGraph

from app.agents.pipeline_runners import (
    PipelineAgents,
    run_copywriter_stage,
    run_requirement_stage,
    run_reviewer_stage,
)
from app.agents.pipeline_state import (
    PipelineState,
    build_failure_result,
    build_success_result,
    init_pipeline_state,
)
from app.utils.logger import logger


_agents: PipelineAgents | None = None
_copy_pipeline_graph = None


def _get_agents() -> PipelineAgents:
    global _agents
    if _agents is None:
        _agents = PipelineAgents()
    return _agents


def _requirement_node(state: PipelineState) -> dict:
    """节点 1：需求理解。"""
    db = state["db"]
    return run_requirement_stage(db, _get_agents(), state)


def _copywriter_node(state: PipelineState) -> dict:
    """节点 2：文案创作。"""
    db = state["db"]
    return run_copywriter_stage(db, _get_agents(), state)


def _reviewer_node(state: PipelineState) -> dict:
    """节点 3：审核优化。"""
    db = state["db"]
    return run_reviewer_stage(db, _get_agents(), state)


def _finalize_node(state: PipelineState) -> dict:
    """节点 4：成功收尾，写入统一 result。"""
    result = build_success_result(state)
    logger.info(
        f"LangGraph 主流程完成: task_id={state.get('task_id')}, "
        f"final_copy_id={result.get('final_copy_id')}"
    )
    return {"result": result}


def _mark_failed_node(state: PipelineState) -> dict:
    """节点 5：创作失败收尾。"""
    result = build_failure_result(state)
    logger.error(
        f"LangGraph 主流程失败: task_id={state.get('task_id')}, "
        f"error={result.get('error')}"
    )
    return {"result": result}


def _route_after_copywriter(
    state: PipelineState,
) -> Literal["reviewer", "mark_failed"]:
    """copywriter 后条件路由：失败则直接结束，成功则进入审核。"""
    if state.get("abort"):
        return "mark_failed"
    return "reviewer"


def build_copy_pipeline_graph():
    """
    构建并编译文案主流程 StateGraph。

    返回值：
        编译后的图，供 run_copy_pipeline 单例 invoke。
    """
    graph = StateGraph(PipelineState)

    graph.add_node("requirement", _requirement_node)
    graph.add_node("copywriter", _copywriter_node)
    graph.add_node("reviewer", _reviewer_node)
    graph.add_node("finalize", _finalize_node)
    graph.add_node("mark_failed", _mark_failed_node)

    graph.set_entry_point("requirement")
    graph.add_edge("requirement", "copywriter")
    graph.add_conditional_edges(
        "copywriter",
        _route_after_copywriter,
        {
            "reviewer": "reviewer",
            "mark_failed": "mark_failed",
        },
    )
    graph.add_edge("reviewer", "finalize")
    graph.add_edge("finalize", END)
    graph.add_edge("mark_failed", END)

    return graph.compile()


def run_copy_pipeline(db, task_id: int) -> dict:
    """
    【主流程图 · 对外唯一入口】执行 LangGraph 文案生成流水线。

    参数：
        db: SQLAlchemy Session
        task_id: 任务 ID

    返回：
        与 OrchestrationEngine.run / AgentOrchestrator.run 对齐的 dict。
    """
    global _copy_pipeline_graph

    state, early_error = init_pipeline_state(db, task_id)
    if early_error:
        return early_error
    assert state is not None

    logger.info(f"{'=' * 50}")
    logger.info(f"LangGraph 主流程开始: task_id={task_id}")
    logger.info(f"{'=' * 50}")

    if _copy_pipeline_graph is None:
        _copy_pipeline_graph = build_copy_pipeline_graph()

    final_state = _copy_pipeline_graph.invoke(state)
    result = final_state.get("result")
    if result:
        return result

    if final_state.get("abort"):
        return build_failure_result(final_state)
    return build_success_result(final_state)
