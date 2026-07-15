"""受约束的编排决策策略。

LLM Planner 负责提出计划，本模块用确定性规则决定模式映射、安全步骤是否允许跳过，
以及终稿是否通过质量门控。这样既保留 Agent 自主性，又避免模型绕过合规和审核。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ExecutionMode = Literal["fixed", "agentic"]
GateAction = Literal["finalize", "rewrite", "awaiting_human"]

_PRODUCT_MODE_MAP: dict[str, ExecutionMode] = {
    "fast": "fixed",
    "fixed": "fixed",
    "plan": "agentic",
    "agentic": "agentic",
}
_SAFETY_STAGES = frozenset({"verify", "reviewer", "quality_gate"})
_CORE_DIMENSIONS = frozenset({
    "内容相关性",
    "平台适配性",
    "结构完整性",
    "信息密度",
})


@dataclass(frozen=True)
class QualityGateDecision:
    passed: bool
    action: GateAction
    failed_checks: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "action": self.action,
            "failed_checks": list(self.failed_checks),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StepSkipDecision:
    should_skip: bool
    reason: str = ""


def resolve_execution_mode(requested_mode: str | None) -> ExecutionMode:
    """把用户可理解的 Fast/Plan 映射为内部固定/Agentic 模式。"""
    normalized = str(requested_mode or "").strip().lower()
    return _PRODUCT_MODE_MAP.get(normalized, "fixed")


def decide_step_skip(
    state: dict[str, Any],
    step: dict[str, Any],
) -> StepSkipDecision:
    """只跳过可幂等复用的业务步骤；验证、审核等安全步骤永不跳过。"""
    stage = str(step.get("stage") or "").strip().lower()
    if stage in _SAFETY_STAGES or not step.get("can_skip", False):
        return StepSkipDecision(False)

    if stage == "requirement" and (state.get("parsed_requirement") or {}).get("topic"):
        return StepSkipDecision(True, "structured_requirement_already_available")
    if stage == "copywriter" and state.get("copy_id") and state.get("copy_content"):
        return StepSkipDecision(True, "draft_already_available")
    if stage == "research" and state.get("evidence_pack"):
        return StepSkipDecision(True, "evidence_pack_already_available")
    return StepSkipDecision(False)


def decide_final_quality_gate(
    state: dict[str, Any],
    *,
    total_threshold: int = 75,
    dimension_threshold: int = 70,
    max_rewrites: int = 1,
) -> QualityGateDecision:
    """终稿发布门控：总分与核心维度同时达标，失败时最多允许一次章节重写。"""
    report = state.get("quality_report") or {}
    failed_checks: list[str] = []

    if state.get("final_copy_id") is None:
        failed_checks.append("final_copy")

    total_score = _safe_score(report.get("total_score", state.get("review_score", 0)))
    # 旧短文任务可能没有结构化 quality_report，沿用 60 分兼容阈值。
    effective_total_threshold = total_threshold if report else 60
    if total_score < effective_total_threshold:
        failed_checks.append("total_score")

    weak_core_dimensions = []
    for dimension in report.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        name = str(dimension.get("name") or "")
        score = _safe_score(dimension.get("score"))
        if name in _CORE_DIMENSIONS and score < dimension_threshold:
            weak_core_dimensions.append(name)
    if weak_core_dimensions:
        failed_checks.append("core_dimensions")

    failed_sections = report.get("failed_sections") or []
    if failed_sections:
        failed_checks.append("failed_sections")

    if not failed_checks:
        return QualityGateDecision(
            passed=True,
            action="finalize",
            reason="quality_gate_passed",
        )

    rewrite_count = max(_safe_score(state.get("rewrite_count")), 0)
    can_rewrite = (
        rewrite_count < max_rewrites
        and bool(failed_sections)
        and "final_copy" not in failed_checks
    )
    if can_rewrite:
        return QualityGateDecision(
            passed=False,
            action="rewrite",
            failed_checks=failed_checks,
            reason="low_score_sections_can_be_rewritten_once",
        )

    return QualityGateDecision(
        passed=False,
        action="awaiting_human",
        failed_checks=failed_checks,
        reason="quality_gate_failed_after_bounded_recovery",
    )


def _safe_score(value: Any) -> int:
    try:
        return max(int(float(value or 0)), 0)
    except (TypeError, ValueError):
        return 0

