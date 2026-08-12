"""LangGraph durable checkpoint、interrupt 与 resume 回归测试。"""

import sqlite3
from pathlib import Path

from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from app.services.langgraph_checkpoint import ParameterizedSqliteSaver


class ApprovalState(TypedDict, total=False):
    value: int
    decision: str


def _build_approval_graph(checkpoint_path: Path):
    def request_approval(state: ApprovalState):
        decision = interrupt({"kind": "approval", "value": state["value"]})
        return {"decision": decision["action"]}

    builder = StateGraph(ApprovalState)
    builder.add_node("request_approval", request_approval)
    builder.set_entry_point("request_approval")
    builder.add_edge("request_approval", END)
    saver = ParameterizedSqliteSaver(checkpoint_path)
    return builder.compile(checkpointer=saver), saver


def test_checkpoint_survives_saver_and_graph_rebuild(tmp_path):
    checkpoint_path = tmp_path / "langgraph-checkpoints.sqlite3"
    config = {"configurable": {"thread_id": "task-42"}}

    first_graph, first_saver = _build_approval_graph(checkpoint_path)
    first_result = first_graph.invoke({"value": 7}, config=config)
    first_saver.close()

    assert first_result["__interrupt__"][0].value == {
        "kind": "approval",
        "value": 7,
    }

    rebuilt_graph, rebuilt_saver = _build_approval_graph(checkpoint_path)
    resumed = rebuilt_graph.invoke(
        Command(resume={"action": "retry"}),
        config=config,
    )
    rebuilt_saver.close()

    assert resumed["value"] == 7
    assert resumed["decision"] == "retry"


def test_saver_uses_bound_parameters_for_untrusted_thread_id(tmp_path):
    checkpoint_path = tmp_path / "langgraph-checkpoints.sqlite3"
    malicious_thread_id = "x'; DROP TABLE checkpoints; --"
    config = {"configurable": {"thread_id": malicious_thread_id}}
    graph, saver = _build_approval_graph(checkpoint_path)

    graph.invoke({"value": 1}, config=config)
    saver.close()

    with sqlite3.connect(checkpoint_path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'"
        ).fetchone()
        row = connection.execute(
            "SELECT thread_id FROM checkpoints WHERE thread_id = ?",
            (malicious_thread_id,),
        ).fetchone()

    assert table == ("checkpoints",)
    assert row == (malicious_thread_id,)
