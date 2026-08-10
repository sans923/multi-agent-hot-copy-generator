"""
文案流水线阶段执行器
====================
AgentOrchestrator 与 LangGraph 主流程图共用，保证两套引擎行为一致。
"""

from typing import Any

from sqlalchemy.orm import Session

from app.agents.copywriter_agent import CopywriterAgent
from app.agents.requirement_agent import RequirementAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.pipeline_state import (
    PipelineState,
    build_failure_result,
    build_fallback_requirement,
    build_success_result,
    init_pipeline_state,
)
from app.models.copy import Copy
from app.models.task import Task, TaskStatus
from app.services.audit_service import write_audit_log
from app.services.longform_mvp_service import build_content_brief, build_outline
from app.utils.logger import logger


class PipelineAgents:
    """流水线内复用的三个 SubAgent 实例。"""

    def __init__(self) -> None:
        self.requirement_agent = RequirementAgent()
        self.copywriter_agent = CopywriterAgent()
        self.reviewer_agent = ReviewerAgent()


def mark_task_failed(db: Session, task_id: int, error_message: str) -> None:
    """将任务标记为失败。"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return
    task.status = TaskStatus.FAILED
    task.error_message = error_message[:500]
    db.commit()
    logger.error(f"任务失败: task_id={task.id}, error={error_message}")


def promote_draft_to_final(
    db: Session,
    copy_id: int | None,
    *,
    task_id: int,
) -> int | None:
    """审核失败时，把初稿升级为终稿（降级处理）。"""
    if not copy_id:
        return None
    query = db.query(Copy).filter(Copy.id == copy_id)
    query = query.filter(Copy.task_id == task_id)
    copy = query.first()
    if not copy:
        return None
    copy.is_final = True
    copy.version = 2
    copy.review_comment = "审核Agent异常，自动采用初稿"
    db.commit()
    logger.info(f"初稿已升级为终稿: copy_id={copy_id}")
    return copy.id


def run_requirement_stage(
    db: Session,
    agents: PipelineAgents,
    state: PipelineState,
) -> dict[str, Any]:
    """Stage 1：需求理解（失败时降级，不 abort）。"""
    task_id = state["task_id"]
    raw_requirement = state["raw_requirement"]
    platform = state["platform"]
    stages = dict(state.get("stages") or {})
    total_tokens = state.get("total_tokens", 0)

    logger.info("[Stage 1/3] 需求理解 Agent 开始...")
    write_audit_log(
        db, task_id, "stage", "requirement_start",
        agent_name="requirement_agent",
        input_summary={"platform": platform, "raw_len": len(raw_requirement)},
    )

    try:
        req_result = agents.requirement_agent.run(
            db=db,
            task_id=task_id,
            raw_requirement=raw_requirement,
            platform=platform,
        )
        stages["requirement"] = {
            "success": req_result.get("success"),
            "tokens_used": req_result.get("tokens_used", 0),
        }
        total_tokens += req_result.get("tokens_used", 0)

        if not req_result.get("success"):
            logger.warning(f"需求理解Agent失败，使用降级方案: {req_result.get('error')}")
            parsed_requirement = build_fallback_requirement(raw_requirement, platform)
            hot_topics: list[dict[str, Any]] = []
            context_messages: list[dict[str, Any]] = []
        else:
            parsed_requirement = req_result.get("parsed_requirement", {})
            hot_topics = req_result.get("hot_topics", [])
            context_messages = req_result.get("messages", [])

        logger.info(
            f"[Stage 1/3] 需求理解完成: "
            f"topic={parsed_requirement.get('topic')}, "
            f"hot_topics={len(hot_topics)}"
        )
        write_audit_log(
            db, task_id, "stage", "requirement_done",
            agent_name="requirement_agent",
            output_summary={
                "success": req_result.get("success"),
                "topic": parsed_requirement.get("topic"),
                "hot_topics": len(hot_topics),
            },
            status="success" if req_result.get("success") else "failed",
        )

        return {
            "parsed_requirement": parsed_requirement,
            "hot_topics": hot_topics,
            "context_messages": context_messages,
            "stages": stages,
            "total_tokens": total_tokens,
        }

    except Exception as exc:
        logger.exception("需求理解Agent异常，使用降级方案")
        write_audit_log(
            db, task_id, "stage", "requirement_error",
            agent_name="requirement_agent",
            status="failed",
            error_message=str(exc),
        )
        stages["requirement"] = {"success": False, "error": str(exc)}
        return {
            "parsed_requirement": build_fallback_requirement(raw_requirement, platform),
            "hot_topics": [],
            "context_messages": [],
            "stages": stages,
            "total_tokens": total_tokens,
        }


def run_copywriter_stage(
    db: Session,
    agents: PipelineAgents,
    state: PipelineState,
) -> dict[str, Any]:
    """Stage 2：文案创作（失败时 abort 整单）。"""
    task_id = state["task_id"]
    stages = dict(state.get("stages") or {})
    total_tokens = state.get("total_tokens", 0)

    logger.info("[Stage 2/3] 文案创作 Agent 开始...")
    write_audit_log(db, task_id, "stage", "copywriter_start", agent_name="copywriter_agent")

    try:
        parsed_requirement = dict(state.get("parsed_requirement") or {})
        selected_style_card_id = state.get("selected_style_card_id")
        if selected_style_card_id:
            from app.models.style_card import StyleCard

            selected_card = db.query(StyleCard).filter(StyleCard.id == selected_style_card_id).first()
            if selected_card:
                parsed_requirement["selected_style_card"] = {
                    "id": selected_card.id,
                    "topic_cluster": selected_card.topic_cluster,
                    "pattern": selected_card.pattern_json,
                    "confidence": float(selected_card.confidence or 0),
                }
                parsed_requirement["writing_pattern"] = selected_card.pattern_json
                write_audit_log(
                    db,
                    task_id,
                    "asset",
                    "style_card_selected",
                    agent_name="copywriter_agent",
                    output_summary={
                        "style_card_id": selected_card.id,
                        "topic_cluster": selected_card.topic_cluster,
                    },
                )
        if state.get("platform") == "toutiao":
            brief = build_content_brief(
                parsed_requirement=parsed_requirement,
                hot_topics=state.get("hot_topics", []),
            )
            outline = build_outline(brief)
            parsed_requirement.update({
                "platform": "toutiao",
                "word_count": brief.target_word_count,
                "content_brief": brief.model_dump(),
                "article_outline": outline.model_dump(),
                "longform_mvp": {
                    "enabled": True,
                    "rewrite_count": 0,
                    "max_rewrites": 1,
                },
            })
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.parsed_requirement = parsed_requirement
                db.commit()
            stages["longform_planning"] = {
                "success": True,
                "section_count": len(outline.sections),
                "target_word_count": brief.target_word_count,
            }
            write_audit_log(
                db,
                task_id,
                "stage",
                "longform_planning_done",
                agent_name="copywriter_agent",
                output_summary={
                    "section_count": len(outline.sections),
                    "target_word_count": brief.target_word_count,
                    "selected_title": outline.selected_title,
                },
            )

        copy_result = agents.copywriter_agent.run(
            db=db,
            task_id=task_id,
            parsed_requirement=parsed_requirement,
            hot_topics=state.get("hot_topics", []),
            context_messages=state.get("context_messages", []),
            rewrite_hint=state.get("rewrite_hint") or "",
        )
        stages["copywriter"] = {
            "success": copy_result.get("success"),
            "copy_id": copy_result.get("copy_id"),
            "tokens_used": copy_result.get("tokens_used", 0),
        }
        total_tokens += copy_result.get("tokens_used", 0)

        if not copy_result.get("success"):
            error_msg = copy_result.get("error", "文案创作失败")
            write_audit_log(
                db, task_id, "stage", "copywriter_failed",
                agent_name="copywriter_agent",
                status="failed",
                error_message=error_msg,
            )
            mark_task_failed(db, task_id, error_msg)
            logger.error(f"[Stage 2/3] 文案创作失败: {error_msg}")
            return {
                "stages": stages,
                "total_tokens": total_tokens,
                "abort": True,
                "error": error_msg,
            }

        copy_id = copy_result.get("copy_id")
        logger.info(f"[Stage 2/3] 文案创作完成: copy_id={copy_id}")
        write_audit_log(
            db, task_id, "stage", "copywriter_done",
            agent_name="copywriter_agent",
            output_summary={"copy_id": copy_id},
        )
        return {
            "copy_id": copy_id,
            "copy_content": copy_result.get("copy_content", ""),
            "parsed_requirement": parsed_requirement,
            "content_brief": parsed_requirement.get("content_brief", {}),
            "article_outline": parsed_requirement.get("article_outline", {}),
            "stages": stages,
            "total_tokens": total_tokens,
            "abort": False,
        }

    except Exception as exc:
        error_msg = f"文案创作Agent异常: {str(exc)}"
        logger.exception(error_msg)
        mark_task_failed(db, task_id, error_msg)
        stages["copywriter"] = {"success": False, "error": str(exc)}
        return {
            "stages": stages,
            "total_tokens": total_tokens,
            "abort": True,
            "error": error_msg,
        }


def run_reviewer_stage(
    db: Session,
    agents: PipelineAgents,
    state: PipelineState,
) -> dict[str, Any]:
    """Stage 3：审核优化（失败时降级为初稿终稿，不 abort）。"""
    task_id = state["task_id"]
    copy_id = state.get("copy_id")
    stages = dict(state.get("stages") or {})
    total_tokens = state.get("total_tokens", 0)

    logger.info("[Stage 3/3] 审核优化 Agent 开始...")
    write_audit_log(db, task_id, "stage", "reviewer_start", agent_name="reviewer_agent")

    try:
        review_result = agents.reviewer_agent.run(
            db=db,
            task_id=task_id,
            copy_id=copy_id,
            copy_content=state.get("copy_content", ""),
            parsed_requirement=state.get("parsed_requirement", {}),
            hot_topics=state.get("hot_topics", []),
        )
        stages["reviewer"] = {
            "success": review_result.get("success"),
            "review_score": review_result.get("review_score"),
            "need_optimization": review_result.get("need_optimization"),
            "tokens_used": review_result.get("tokens_used", 0),
        }
        total_tokens += review_result.get("tokens_used", 0)

        if not review_result.get("success"):
            logger.warning(
                f"审核Agent失败，使用初稿作为终稿: {review_result.get('error')}"
            )
            final_copy_id = promote_draft_to_final(db, copy_id, task_id=task_id)
            review_score = 0.0
        else:
            final_copy_id = review_result.get("final_copy_id", copy_id)
            review_score = float(review_result.get("review_score", 0) or 0)

        quality_report = review_result.get("quality_report") or {}
        rewrite_count = max(
            int(state.get("rewrite_count", 0) or 0),
            int(review_result.get("rewrite_count", 0) or 0),
        )
        parsed_requirement = dict(state.get("parsed_requirement") or {})
        if parsed_requirement.get("platform") == "toutiao":
            longform_meta = dict(parsed_requirement.get("longform_mvp") or {})
            longform_meta.update({
                "quality_report": quality_report,
                "rewrite_count": rewrite_count,
                "max_rewrites": 1,
            })
            parsed_requirement["longform_mvp"] = longform_meta
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.parsed_requirement = parsed_requirement
                db.commit()

        logger.info(
            f"[Stage 3/3] 审核优化完成: "
            f"score={review_score}, final_copy_id={final_copy_id}"
        )
        write_audit_log(
            db, task_id, "stage", "reviewer_done",
            agent_name="reviewer_agent",
            output_summary={
                "review_score": review_score,
                "final_copy_id": final_copy_id,
                "success": review_result.get("success"),
                "rewrite_count": rewrite_count,
            },
            status="success" if review_result.get("success") else "failed",
        )
        return {
            "final_copy_id": final_copy_id,
            "review_score": review_score,
            "quality_report": quality_report,
            "rewrite_count": rewrite_count,
            "parsed_requirement": parsed_requirement,
            "stages": stages,
            "total_tokens": total_tokens,
        }

    except Exception as exc:
        logger.exception("审核Agent异常，使用初稿作为终稿")
        stages["reviewer"] = {"success": False, "error": str(exc)}
        final_copy_id = promote_draft_to_final(db, copy_id, task_id=task_id)
        return {
            "final_copy_id": final_copy_id,
            "review_score": 0.0,
            "stages": stages,
            "total_tokens": total_tokens,
        }


def run_full_pipeline(db: Session, task_id: int, agents: PipelineAgents | None = None) -> dict[str, Any]:
    """
    执行完整三阶段流水线（native 与 LangGraph 均可调用）。

    返回结构与 OrchestrationEngine.run 对齐。
    """
    agents = agents or PipelineAgents()

    logger.info(f"{'=' * 50}")
    logger.info(f"开始执行 Agent 编排流程: task_id={task_id}")
    logger.info(f"{'=' * 50}")

    write_audit_log(
        db, task_id, "orchestration", "pipeline_start",
        input_summary={"mode": "fixed"},
    )

    state, early_error = init_pipeline_state(db, task_id)
    if early_error:
        return early_error
    assert state is not None

    state = _merge_state(state, run_requirement_stage(db, agents, state))
    if state.get("abort"):
        return build_failure_result(state)

    state = _merge_state(state, run_copywriter_stage(db, agents, state))
    if state.get("abort"):
        return build_failure_result(state)

    state = _merge_state(state, run_reviewer_stage(db, agents, state))

    result = build_success_result(state)
    write_audit_log(
        db, task_id, "orchestration", "pipeline_complete",
        output_summary={
            "success": True,
            "final_copy_id": result.get("final_copy_id"),
            "review_score": result.get("review_score"),
            "total_tokens": result.get("total_tokens"),
        },
    )

    logger.info(
        f"{'=' * 50}\n"
        f"Agent 编排流程完成: task_id={task_id}\n"
        f"  最终文案: copy_id={state.get('final_copy_id')}\n"
        f"  审核得分: {state.get('review_score')}\n"
        f"  总消耗token: {state.get('total_tokens')}\n"
        f"{'=' * 50}"
    )
    return result


def _merge_state(state: PipelineState, updates: dict[str, Any]) -> PipelineState:
    merged: PipelineState = dict(state)
    merged.update(updates)
    return merged


def run_lead_pipeline(
    db: Session,
    task_id: int,
    agents: PipelineAgents | None = None,
) -> dict[str, Any]:
    """Lead Agent 总控编排（native / langgraph-lead 共用入口）。"""
    from app.agents.lead_agent import LeadAgent

    return LeadAgent(agents=agents).run(db=db, task_id=task_id, agents=agents)
