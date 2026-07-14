"""
Lead Agent 流水线运行时上下文
==============================
委派类 Skill 通过 ContextVar 读写当前 PipelineState，避免在 Skill 参数里传递复杂 state。
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agents.pipeline_state import PipelineState

if TYPE_CHECKING:
    from app.agents.pipeline_runners import PipelineAgents


@dataclass
class ActivePipeline:
    """一次 Lead 编排会话内的可变 state + SubAgent 实例。"""

    state: PipelineState
    agents: PipelineAgents

    def merge(self, updates: dict[str, Any]) -> None:
        if "stages" in updates and isinstance(updates["stages"], dict):
            merged_stages = dict(self.state.get("stages") or {})
            for key, value in updates["stages"].items():
                if (
                    key in merged_stages
                    and isinstance(merged_stages[key], dict)
                    and isinstance(value, dict)
                ):
                    merged_stages[key] = {**merged_stages[key], **value}
                else:
                    merged_stages[key] = value
            updates = {**updates, "stages": merged_stages}
        self.state.update(updates)


_current_pipeline: ContextVar[ActivePipeline | None] = ContextVar(
    "current_pipeline",
    default=None,
)


def set_active_pipeline(active: ActivePipeline) -> object:
    """绑定当前上下文，返回 reset token。"""
    return _current_pipeline.set(active)


def reset_active_pipeline(token: object) -> None:
    """恢复之前的上下文。"""
    _current_pipeline.reset(token)


def get_active_pipeline() -> ActivePipeline | None:
    """获取当前 Lead 流水线上下文。"""
    return _current_pipeline.get()


def mark_stage_delegated(stages: dict[str, Any], stage_key: str) -> dict[str, Any]:
    """为阶段结果标注 Lead 委派来源。"""
    if stage_key in stages and isinstance(stages[stage_key], dict):
        stages[stage_key] = {**stages[stage_key], "delegated_by": "lead_agent"}
    return stages
