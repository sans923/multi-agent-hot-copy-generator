"""
Lead Agent（总控）
=================
DeerFlow 风格：Lead 只持有委派类 tools，按约束顺序调度 SubAgent。

固定路径（system prompt 强制）：
  delegate_to_requirement → delegate_to_copywriter → delegate_to_reviewer → finish_task
"""

import json

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.agents.pipeline_context import (
    ActivePipeline,
    reset_active_pipeline,
    set_active_pipeline,
)
from app.agents.pipeline_runners import PipelineAgents
from app.agents.pipeline_state import (
    build_failure_result,
    build_success_result,
    init_pipeline_state,
)
from app.skills import LEAD_AGENT_SKILLS
from app.utils.logger import logger


class LeadAgent(BaseAgent):
    """
    总控 Lead Agent：通过委派 Skill 驱动三阶段 SubAgent。
    """

    def __init__(self, agents: PipelineAgents | None = None):
        super().__init__()
        self._pipeline_agents = agents or PipelineAgents()

    @property
    def name(self) -> str:
        return "lead_agent"

    @property
    def skill_names(self) -> list[str]:
        return LEAD_AGENT_SKILLS

    @property
    def max_tool_calls(self) -> int:
        return 6

    @property
    def system_prompt(self) -> str:
        return """你是多智能体文案生成系统的总控 Lead Agent（Orchestrator Lead）。

你的职责：
1. 读取当前流水线进度摘要
2. 按固定顺序委派 SubAgent，绝不跳过或乱序
3. 全部阶段完成后调用 finish_task 结束

【强制顺序】
1. delegate_to_requirement   — 需求理解 SubAgent
2. delegate_to_copywriter    — 文案创作 SubAgent（requirement 之后）
3. delegate_to_reviewer      — 审核优化 SubAgent（copywriter 成功之后）
4. finish_task               — 收尾

【规则】
- 你只有委派类工具，不能直接写文案或调业务 Skill
- 若 copywriter 返回 abort=true，直接 finish_task，不要调用 reviewer
- 每个阶段只委派一次，不要重复委派已完成的阶段
- 不要向用户追问，按工具返回结果继续下一步"""

    def run(self, db: Session, task_id: int, **kwargs) -> dict:
        state, early_error = init_pipeline_state(db, task_id)
        if early_error:
            return early_error
        assert state is not None

        agents = kwargs.get("agents") or self._pipeline_agents
        active = ActivePipeline(state=state, agents=agents)
        token = set_active_pipeline(active)

        logger.info(f"{'=' * 50}")
        logger.info(f"Lead Agent 编排开始: task_id={task_id}")
        logger.info(f"{'=' * 50}")

        try:
            user_message = self._build_user_message(active.state)
            loop_result = self._run_loop(
                db=db,
                task_id=task_id,
                user_message=user_message,
            )

            active.state["total_tokens"] = (
                active.state.get("total_tokens", 0)
                + loop_result.get("tokens_used", 0)
            )

            if active.state.get("result"):
                return active.state["result"]

            finish_payload = self._extract_finish_payload(loop_result)
            if finish_payload:
                if finish_payload.get("finished"):
                    return finish_payload
                if "success" in finish_payload:
                    return finish_payload

            if active.state.get("abort"):
                return build_failure_result(active.state)

            if active.state.get("final_copy_id") is not None:
                result = build_success_result(active.state)
                result["orchestration_mode"] = "lead"
                return result

            if not loop_result.get("success"):
                return {
                    "success": False,
                    "task_id": task_id,
                    "error": loop_result.get("error", "Lead Agent 执行失败"),
                    "stages": active.state.get("stages", {}),
                    "total_tokens": active.state.get("total_tokens", 0)
                    + loop_result.get("tokens_used", 0),
                }

            return {
                "success": False,
                "task_id": task_id,
                "error": "Lead Agent 未调用 finish_task 完成收尾",
                "stages": active.state.get("stages", {}),
                "total_tokens": active.state.get("total_tokens", 0),
            }

        finally:
            reset_active_pipeline(token)

    def _build_user_message(self, state: dict) -> str:
        stages = state.get("stages") or {}
        completed = list(stages.keys())
        return f"""请完成 task_id={state['task_id']} 的文案生成流水线。

【任务信息】
- 原始需求：{state.get('raw_requirement', '')[:200]}
- 目标平台：{state.get('platform', 'weibo')}
- 已完成阶段：{completed or '无'}

请从第一个尚未完成的阶段开始，按顺序委派 SubAgent，最后 finish_task。"""

    def _extract_finish_payload(self, loop_result: dict) -> dict | None:
        for tool_result in loop_result.get("tool_results", []):
            if tool_result.get("skill_name") != "finish_task":
                continue
            result = tool_result.get("result") or {}
            if result.get("finished"):
                return result
        return None
