"""
外部验证服务
============
规则优先验证输出是否满足用户目标；软失败时调用 Judge 模型（Phase 2）。
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.judge_service import judge_goal_alignment
from app.services.audit_service import write_audit_log
from app.utils.logger import logger

_SOFT_CHECK_KEYS = frozenset({"topic_match", "length_ok"})


def verify_draft(state: dict[str, Any]) -> dict[str, Any]:
    """
    初稿规则验证（copywriter 之后）。

    检查：正文非空、长度合理、主题词部分命中。
    软失败（topic/length）且开启 Judge 时，调用 Judge 模型兜底。
    """
    copy_content = (state.get("copy_content") or "").strip()
    parsed = state.get("parsed_requirement") or {}
    topic = (parsed.get("topic") or state.get("raw_requirement") or "")[:30]
    word_count = int(parsed.get("word_count") or settings.TASK_SIMPLE_MAX_WORDS)
    min_len = max(15, int(word_count * 0.15))
    max_len = max(min_len + 100, int(word_count * 3))

    checks: dict[str, bool] = {
        "has_content": len(copy_content) >= 10,
        "length_ok": min_len <= len(copy_content) <= max_len,
    }

    if topic and len(topic) >= 2:
        topic_hit = any(
            chunk in copy_content
            for chunk in [topic[:4], topic[:2]]
            if len(chunk) >= 2
        )
        checks["topic_match"] = topic_hit
    else:
        checks["topic_match"] = True

    failed = [k for k, v in checks.items() if not v]
    passed = len(failed) == 0

    result: dict[str, Any] = {
        "passed": passed,
        "checks": checks,
        "failed_checks": failed,
        "source": "rules",
        "stage": "verify_draft",
    }

    if passed:
        logger.info("初稿验证: passed=True (rules)")
        return result

    # 硬失败：无内容
    if "has_content" in failed:
        logger.info(f"初稿验证: passed=False, failed={failed}")
        return result

    # 软失败：仅 topic/length → 尝试 Judge
    if (
        settings.ENABLE_JUDGE_VERIFY
        and set(failed).issubset(_SOFT_CHECK_KEYS)
    ):
        judge = judge_goal_alignment(
            raw_requirement=state.get("raw_requirement") or "",
            copy_content=copy_content,
            platform=state.get("platform") or parsed.get("platform") or "weibo",
        )
        if judge.get("passed"):
            result["passed"] = True
            result["source"] = "rules+judge"
            result["judge"] = judge
            logger.info(f"初稿验证: Judge 兜底通过, score={judge.get('score')}")
            write_audit_log(
                state.get("db"),
                state.get("task_id"),
                "judge",
                "goal_alignment",
                input_summary={"platform": state.get("platform")},
                output_summary={
                    "passed": judge.get("passed"),
                    "score": judge.get("score"),
                    "reason": judge.get("reason"),
                },
            )
            return result
        result["judge"] = judge
        result["source"] = "rules+judge"
        write_audit_log(
            state.get("db"),
            state.get("task_id"),
            "judge",
            "goal_alignment",
            output_summary={"passed": False, "reason": judge.get("reason")},
            status="failed",
        )

    logger.info(f"初稿验证: passed=False, failed={failed}")
    return result


def verify_final(state: dict[str, Any]) -> dict[str, Any]:
    """
    终稿规则验证（reviewer 之后）。

    检查：终稿 ID 存在、审核分达标（若有）。
    """
    final_copy_id = state.get("final_copy_id")
    review_score = float(state.get("review_score") or 0)
    stages = state.get("stages") or {}
    reviewer_stage = stages.get("reviewer") or {}

    checks: dict[str, bool] = {
        "has_final_copy": final_copy_id is not None,
        "reviewer_ran": reviewer_stage.get("success") is not False,
    }
    if review_score > 0:
        checks["score_ok"] = review_score >= 60

    compliance = reviewer_stage.get("compliance_passed")
    plagiarism = reviewer_stage.get("plagiarism_passed")
    if compliance is not None:
        checks["compliance"] = bool(compliance)
    if plagiarism is not None:
        checks["plagiarism"] = bool(plagiarism)

    failed = [k for k, v in checks.items() if not v]
    passed = len(failed) == 0

    result = {
        "passed": passed,
        "checks": checks,
        "failed_checks": failed,
        "source": "rules",
        "stage": "verify_final",
    }
    write_audit_log(
        state.get("db"),
        state.get("task_id"),
        "verify",
        "verify_final",
        output_summary={
            "passed": passed,
            "failed_checks": failed,
            "checks": checks,
        },
        status="success" if passed else "failed",
    )
    logger.info(f"终稿验证: passed={passed}, failed={failed}")
    return result


def verify_step(state: dict[str, Any], stage: str) -> dict[str, Any]:
    """按 stage 分发验证。"""
    if stage == "verify":
        step_id = _current_step_id(state)
        if step_id == "verify_draft" or state.get("copy_content"):
            return verify_draft(state)
        return verify_final(state)
    return {"passed": True, "checks": {}, "source": "skip", "stage": stage}


def _current_step_id(state: dict[str, Any]) -> str:
    plan = state.get("plan") or {}
    steps = plan.get("steps") or []
    idx = state.get("current_step") or 0
    if 0 <= idx < len(steps):
        return steps[idx].get("step_id") or ""
    return ""
