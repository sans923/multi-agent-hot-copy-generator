"""Fast/Plan 双模式与有边界自治策略测试。

用户旅程：创建者可以按任务选择稳定快速模式或自主规划模式，并能看到系统为什么
通过、跳过或停止，而不是让 LLM 任意改变安全关键步骤。
"""

from app.services.orchestration_policy import (
    decide_final_quality_gate,
    decide_step_skip,
    resolve_execution_mode,
)


def test_execution_mode_maps_product_modes_to_engines():
    assert resolve_execution_mode("fast") == "fixed"
    assert resolve_execution_mode("plan") == "agentic"


def test_execution_mode_rejects_unknown_values_safely():
    assert resolve_execution_mode("anything") == "fixed"
    assert resolve_execution_mode(None) == "fixed"


def test_quality_gate_passes_only_when_total_and_dimensions_pass():
    decision = decide_final_quality_gate({
        "final_copy_id": 10,
        "review_score": 82,
        "quality_report": {
            "total_score": 82,
            "dimensions": [
                {"name": "内容相关性", "score": 85},
                {"name": "平台适配性", "score": 76},
            ],
            "failed_sections": [],
        },
    })

    assert decision.passed is True
    assert decision.action == "finalize"
    assert decision.failed_checks == []


def test_quality_gate_blocks_high_total_with_weak_core_dimension():
    decision = decide_final_quality_gate({
        "final_copy_id": 10,
        "review_score": 80,
        "rewrite_count": 1,
        "quality_report": {
            "total_score": 80,
            "dimensions": [
                {"name": "内容相关性", "score": 58},
                {"name": "标题吸引力", "score": 95},
            ],
            "failed_sections": [],
        },
    })

    assert decision.passed is False
    assert decision.action == "awaiting_human"
    assert "core_dimensions" in decision.failed_checks


def test_quality_gate_requests_one_rewrite_before_human_escalation():
    state = {
        "final_copy_id": 10,
        "review_score": 68,
        "rewrite_count": 0,
        "quality_report": {
            "total_score": 68,
            "dimensions": [{"name": "内容相关性", "score": 68}],
            "failed_sections": [{"section_id": "s2", "score": 60}],
        },
    }

    first = decide_final_quality_gate(state)
    state["rewrite_count"] = 1
    second = decide_final_quality_gate(state)

    assert first.action == "rewrite"
    assert second.action == "awaiting_human"


def test_completed_idempotent_steps_can_skip_but_safety_steps_cannot():
    requirement = decide_step_skip(
        {"parsed_requirement": {"topic": "AI"}},
        {"step_id": "requirement", "stage": "requirement", "can_skip": True},
    )
    reviewer = decide_step_skip(
        {"final_copy_id": 12},
        {"step_id": "reviewer", "stage": "reviewer", "can_skip": True},
    )

    assert requirement.should_skip is True
    assert requirement.reason == "structured_requirement_already_available"
    assert reviewer.should_skip is False

