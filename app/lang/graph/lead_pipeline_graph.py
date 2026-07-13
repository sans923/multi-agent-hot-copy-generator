"""
LangGraph：Lead Agent【总控图】
================================
单节点图：lead → END，内部由 Lead Agent 通过委派 Skill 驱动 SubAgent。

与 copy_pipeline_graph（固定三节点）并列，由 ORCHESTRATION_MODE=lead 切换。
"""

from langgraph.graph import END, StateGraph

from app.agents.pipeline_runners import run_lead_pipeline
from app.agents.pipeline_state import PipelineState, init_pipeline_state
from app.utils.logger import logger


_lead_pipeline_graph = None


def _lead_node(state: PipelineState) -> dict:
    """Lead 总控节点：委派 SubAgent 完成全流程。"""
    db = state["db"]
    task_id = state["task_id"]
    result = run_lead_pipeline(db=db, task_id=task_id)
    return {"result": result}


def build_lead_pipeline_graph():
    """构建 Lead 单节点 StateGraph。"""
    graph = StateGraph(PipelineState)
    graph.add_node("lead", _lead_node)
    graph.set_entry_point("lead")
    graph.add_edge("lead", END)
    return graph.compile()


def run_lead_pipeline_graph(db, task_id: int) -> dict:
    """
    【Lead 图 · 对外入口】LangGraph 包装 Lead Agent 编排。

    与 run_copy_pipeline 返回结构一致。
    """
    global _lead_pipeline_graph

    state, early_error = init_pipeline_state(db, task_id)
    if early_error:
        return early_error
    assert state is not None

    logger.info(f"{'=' * 50}")
    logger.info(f"LangGraph Lead 主流程开始: task_id={task_id}")
    logger.info(f"{'=' * 50}")

    if _lead_pipeline_graph is None:
        _lead_pipeline_graph = build_lead_pipeline_graph()

    final_state = _lead_pipeline_graph.invoke(state)
    result = final_state.get("result")
    if result:
        return result
    return final_state.get("result") or {"success": False, "task_id": task_id, "error": "Lead 图未返回结果"}
