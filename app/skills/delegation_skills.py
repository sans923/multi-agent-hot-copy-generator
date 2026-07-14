"""
Lead Agent 委派类 Skill
=======================
Lead 只持有委派工具，不直接调用业务 Skill；具体执行由 SubAgent 阶段 runner 完成。
"""

from sqlalchemy.orm import Session

from app.agents.pipeline_context import get_active_pipeline, mark_stage_delegated
from app.agents.pipeline_state import build_failure_result, build_success_result
from app.skills.base import BaseSkill


def _get_stage_runners():
    from app.agents.pipeline_runners import (
        run_copywriter_stage,
        run_requirement_stage,
        run_reviewer_stage,
    )
    return run_requirement_stage, run_copywriter_stage, run_reviewer_stage


def _require_active_pipeline():
    active = get_active_pipeline()
    if active is None:
        return None, {
            "success": False,
            "error": "无活动流水线上下文，请由 Lead Agent 发起委派",
        }
    return active, None


class DelegateToRequirementSkill(BaseSkill):
    """委派需求理解 SubAgent。"""

    @property
    def name(self) -> str:
        return "delegate_to_requirement"

    @property
    def description(self) -> str:
        return (
            "委派需求理解 SubAgent：解析用户原始需求并搜索相关热榜。"
            "文案流水线第一步，必须在 copywriter 之前调用。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "委派原因（可选，便于日志）",
                }
            },
            "required": [],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        active, error = _require_active_pipeline()
        if error:
            return error

        run_requirement_stage, _, _ = _get_stage_runners()
        updates = run_requirement_stage(db, active.agents, active.state)
        active.merge(updates)
        mark_stage_delegated(active.state.setdefault("stages", {}), "requirement")

        return {
            "success": True,
            "stage": "requirement",
            "delegated_to": "requirement_agent",
            "topic": active.state.get("parsed_requirement", {}).get("topic"),
            "hot_topics_count": len(active.state.get("hot_topics") or []),
            "abort": active.state.get("abort", False),
        }


class DelegateToCopywriterSkill(BaseSkill):
    """委派文案创作 SubAgent。"""

    @property
    def name(self) -> str:
        return "delegate_to_copywriter"

    @property
    def description(self) -> str:
        return (
            "委派文案创作 SubAgent：生成文案初稿并保存。"
            "必须在 delegate_to_requirement 之后、reviewer 之前调用。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "委派原因（可选）",
                }
            },
            "required": [],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        active, error = _require_active_pipeline()
        if error:
            return error

        if not active.state.get("parsed_requirement"):
            return {
                "success": False,
                "error": "尚未完成需求理解，不能委派文案创作",
            }

        _, run_copywriter_stage, _ = _get_stage_runners()
        updates = run_copywriter_stage(db, active.agents, active.state)
        active.merge(updates)
        mark_stage_delegated(active.state.setdefault("stages", {}), "copywriter")

        return {
            "success": updates.get("abort") is not True,
            "stage": "copywriter",
            "delegated_to": "copywriter_agent",
            "copy_id": active.state.get("copy_id"),
            "abort": active.state.get("abort", False),
            "error": active.state.get("error"),
        }


class DelegateToReviewerSkill(BaseSkill):
    """委派审核优化 SubAgent。"""

    @property
    def name(self) -> str:
        return "delegate_to_reviewer"

    @property
    def description(self) -> str:
        return (
            "委派审核优化 SubAgent：评分、润色并保存终稿。"
            "必须在 delegate_to_copywriter 成功之后调用。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "委派原因（可选）",
                }
            },
            "required": [],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        active, error = _require_active_pipeline()
        if error:
            return error

        if active.state.get("abort"):
            return {
                "success": False,
                "error": "文案创作已失败，不能进入审核阶段",
                "abort": True,
            }

        if not active.state.get("copy_id"):
            return {
                "success": False,
                "error": "尚未生成文案初稿，不能委派审核",
            }

        _, _, run_reviewer_stage = _get_stage_runners()
        updates = run_reviewer_stage(db, active.agents, active.state)
        active.merge(updates)
        mark_stage_delegated(active.state.setdefault("stages", {}), "reviewer")

        return {
            "success": True,
            "stage": "reviewer",
            "delegated_to": "reviewer_agent",
            "final_copy_id": active.state.get("final_copy_id"),
            "review_score": active.state.get("review_score"),
        }


class FinishTaskSkill(BaseSkill):
    """Lead 确认流水线结束。"""

    @property
    def name(self) -> str:
        return "finish_task"

    @property
    def description(self) -> str:
        return (
            "在三阶段 SubAgent 全部委派完成后调用，结束 Lead 编排并返回最终结果。"
            "若 copywriter 阶段 abort=true，也应调用本工具结束任务。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "任务收尾摘要（可选）",
                }
            },
            "required": [],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        active, error = _require_active_pipeline()
        if error:
            return error

        state = active.state
        stages = state.get("stages") or {}

        if state.get("abort"):
            result = build_failure_result(state)
            state["result"] = result
            return {
                "success": False,
                "finished": True,
                **result,
            }

        if "requirement" not in stages:
            return {"success": False, "error": "尚未委派需求理解阶段"}
        if "copywriter" not in stages:
            return {"success": False, "error": "尚未委派文案创作阶段"}
        if "reviewer" not in stages:
            return {"success": False, "error": "尚未委派审核优化阶段"}

        result = build_success_result(state)
        result["orchestration_mode"] = "lead"
        state["result"] = result
        return {
            "success": True,
            "finished": True,
            **result,
        }
