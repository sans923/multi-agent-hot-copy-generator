"""
文案生成流水线共享状态（PipelineState）
========================================
native 编排器、LangGraph 主流程图与 Agentic 图共用。
"""

import time
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from app.config import settings


class PlanStep(TypedDict, total=False):
    step_id: str
    stage: str
    description: str
    mergeable: bool


class PipelineState(TypedDict, total=False):
    """
    多 Agent 文案流水线共享状态。

    注意：db 为运行时注入的 SQLAlchemy Session，不参与 checkpoint 序列化。
    """

    db: Session
    task_id: int
    raw_requirement: str
    platform: str

    parsed_requirement: dict[str, Any]
    hot_topics: list[dict[str, Any]]
    context_messages: list[dict[str, Any]]

    copy_id: int | None
    copy_content: str
    final_copy_id: int | None
    review_score: float
    content_brief: dict[str, Any]
    article_outline: dict[str, Any]
    quality_report: dict[str, Any]
    rewrite_count: int

    total_tokens: int
    stages: dict[str, Any]

    abort: bool
    error: str | None
    result: dict[str, Any]

    # --- Agentic 扩展字段 ---
    task_mode: str                    # simple | complex | unknown
    classify_reasons: list[str]
    plan: dict[str, Any]              # {steps, source, reasoning, ...}
    current_step: int
    step_count: int
    retry_count: int
    reflect_count: int
    reflect_notes: list[str]
    rewrite_hint: str
    failure_level: str | None         # retry | local | global | human
    verification: dict[str, Any]
    deadline_ts: float
    max_steps: int
    last_step_failed: bool
    awaiting_human: bool


def init_pipeline_state(db: Session, task_id: int) -> tuple[PipelineState | None, dict | None]:
    """
    从数据库加载任务并初始化 PipelineState。

    返回：
        (state, None) 成功；
        (None, error_dict) 任务不存在。
    """
    from app.models.task import Task

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return None, {"success": False, "error": f"任务 {task_id} 不存在", "task_id": task_id}

    platform = task.platform.value if task.platform else "weibo"
    return {
        "db": db,
        "task_id": task_id,
        "raw_requirement": task.raw_requirement,
        "platform": platform,
        "parsed_requirement": {},
        "hot_topics": [],
        "context_messages": [],
        "copy_id": None,
        "copy_content": "",
        "final_copy_id": None,
        "review_score": 0.0,
        "content_brief": {},
        "article_outline": {},
        "quality_report": {},
        "rewrite_count": 0,
        "total_tokens": 0,
        "stages": {},
        "abort": False,
        "error": None,
        "result": {},
        "task_mode": "unknown",
        "classify_reasons": [],
        "plan": {},
        "current_step": 0,
        "step_count": 0,
        "retry_count": 0,
        "reflect_count": 0,
        "reflect_notes": [],
        "rewrite_hint": "",
        "failure_level": None,
        "verification": {},
        "deadline_ts": time.time() + settings.AGENT_TIMEOUT_SEC,
        "max_steps": settings.AGENT_MAX_STEPS,
        "last_step_failed": False,
        "awaiting_human": False,
    }, None


def build_fallback_requirement(raw_requirement: str, platform: str) -> dict[str, Any]:
    """需求理解失败时的降级结构化需求。"""
    return {
        "raw_requirement": raw_requirement,
        "platform": platform,
        "topic": raw_requirement[:20],
        "style": "口语化",
        "keywords": [],
        "word_count": 140,
    }


def build_success_result(state: PipelineState) -> dict[str, Any]:
    """将成功结束的 state 格式化为 OrchestrationEngine 统一返回结构。"""
    return {
        "success": True,
        "task_id": state["task_id"],
        "final_copy_id": state.get("final_copy_id"),
        "review_score": state.get("review_score", 0),
        "total_tokens": state.get("total_tokens", 0),
        "stages": state.get("stages", {}),
        "task_mode": state.get("task_mode"),
        "plan_source": (state.get("plan") or {}).get("source"),
    }


def build_awaiting_human_result(state: PipelineState) -> dict[str, Any]:
    """任务暂停，等待人工介入。"""
    plan = state.get("plan") or {}
    return {
        "success": False,
        "awaiting_human": True,
        "task_id": state.get("task_id"),
        "error": state.get("error") or "需人工介入",
        "stages": state.get("stages", {}),
        "total_tokens": state.get("total_tokens", 0),
        "task_mode": state.get("task_mode"),
        "plan_source": plan.get("source"),
        "failure_level": state.get("failure_level") or "human",
        "current_step": state.get("current_step"),
    }


def build_failure_result(state: PipelineState) -> dict[str, Any]:
    """将失败结束的 state 格式化为 OrchestrationEngine 统一返回结构。"""
    return {
        "success": False,
        "task_id": state.get("task_id"),
        "error": state.get("error") or "文案创作失败",
        "stages": state.get("stages", {}),
        "total_tokens": state.get("total_tokens", 0),
        "task_mode": state.get("task_mode"),
        "failure_level": state.get("failure_level"),
    }


def is_timed_out(state: PipelineState) -> bool:
    """是否超过硬性超时。"""
    deadline = state.get("deadline_ts") or 0
    return time.time() > deadline


def is_step_limit_reached(state: PipelineState) -> bool:
    """是否超过硬性步数上限。"""
    return (state.get("step_count") or 0) >= (state.get("max_steps") or settings.AGENT_MAX_STEPS)
