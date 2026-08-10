"""
任务规划服务
============
复杂任务由 Planner 模型输出结构化 Plan；失败时回退默认三步计划。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.utils.model_roles import get_model_for_role
from app.utils.llm_client import format_llm_error, get_deepseek_client
from app.utils.logger import logger

# 简单任务与 complex 回退共用：与 fixed 流水线对齐
DEFAULT_PIPELINE_STEPS: list[dict[str, Any]] = [
    {
        "step_id": "requirement",
        "stage": "requirement",
        "description": "解析需求并检索相关热榜",
        "mergeable": True,
        "can_skip": True,
    },
    {
        "step_id": "copywriter",
        "stage": "copywriter",
        "description": "检索规律并创作文案初稿",
        "mergeable": False,
        "can_skip": True,
    },
    {
        "step_id": "verify_draft",
        "stage": "verify",
        "description": "规则验证初稿是否满足基本目标",
        "mergeable": False,
        "can_skip": False,
    },
    {
        "step_id": "reviewer",
        "stage": "reviewer",
        "description": "合规检测、洗稿检测、质量评分与终稿保存",
        "mergeable": False,
        "can_skip": False,
    },
]

_PLANNER_SYSTEM = """你是文案生成系统的任务规划器（Planner）。

职责：根据用户需求，输出 JSON 格式的执行计划，供 Executor 按步执行。

规则：
1. stage 只能是：requirement | copywriter | verify | reviewer
2. 简单任务用 4 步默认计划即可；复杂任务可插入额外 verify 或拆分 copywriter（用 description 说明）
3. 不要输出无法执行的 vague 步骤
4. 只输出合法 JSON，不要 markdown 代码块

JSON 格式：
{
  "task_mode": "complex",
  "steps": [
    {"step_id": "requirement", "stage": "requirement", "description": "...", "mergeable": true, "can_skip": true},
    ...
  ],
  "reasoning": "一句话说明规划理由"
}"""


def default_plan(task_mode: str = "simple") -> dict[str, Any]:
    """返回默认计划。"""
    return {
        "task_mode": task_mode,
        "steps": [dict(s) for s in DEFAULT_PIPELINE_STEPS],
        "source": "default",
        "reasoning": "使用默认 requirement → copywriter → verify → reviewer 计划",
    }


def _parse_plan_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return None

    stage_rank = {"requirement": 0, "copywriter": 1, "verify": 2, "reviewer": 3}
    if len(steps) > settings.AGENT_MAX_STEPS:
        return None

    normalized: list[dict[str, Any]] = []
    step_ids: set[str] = set()
    previous_rank = -1
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            return None
        stage = (step.get("stage") or "").strip().lower()
        if stage not in stage_rank or stage_rank[stage] < previous_rank:
            return None
        previous_rank = stage_rank[stage]

        raw_step_id = step.get("step_id")
        step_id = f"step_{idx + 1}" if raw_step_id is None else str(raw_step_id).strip()
        if not step_id or step_id in step_ids:
            return None
        step_ids.add(step_id)

        safety_stage = stage in {"verify", "reviewer"}
        normalized.append({
            "step_id": step_id,
            "stage": stage,
            "description": step.get("description") or "",
            "mergeable": False if safety_stage else bool(step.get("mergeable", False)),
            "can_skip": False if safety_stage else bool(step.get("can_skip", False)),
        })

    required_stages = {"requirement", "copywriter", "verify", "reviewer"}
    if not required_stages.issubset({step["stage"] for step in normalized}):
        return None

    return {
        "task_mode": "complex",
        "steps": normalized,
        "source": "planner_llm",
        "reasoning": data.get("reasoning") or "",
    }


def generate_plan(
    raw_requirement: str,
    platform: str,
    task_mode: str,
    classify_reasons: list[str] | None = None,
) -> dict[str, Any]:
    """
    生成执行计划。

    - simple：直接返回默认计划（不调 LLM）
    - complex：Planner 模型生成；失败回退默认计划
    """
    if task_mode == "simple":
        plan = default_plan("simple")
        logger.info(f"任务分级=simple，使用默认计划，步数={len(plan['steps'])}")
        return plan

    reasons_text = "；".join(classify_reasons or []) or "无"
    user_prompt = (
        f"目标平台：{platform}\n"
        f"任务模式：complex\n"
        f"分级原因：{reasons_text}\n\n"
        f"用户需求：\n{raw_requirement}\n\n"
        "请输出执行计划 JSON。"
    )

    try:
        client = get_deepseek_client()
        response = client.chat.completions.create(
            model=get_model_for_role("planner"),
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content or ""
        parsed = _parse_plan_json(raw)
        if parsed:
            logger.info(
                f"Planner 生成计划: steps={len(parsed['steps'])}, "
                f"model={get_model_for_role('planner')}"
            )
            return parsed
        logger.warning("Planner 输出无法解析，回退默认计划")
    except Exception as exc:
        logger.error(f"Planner 调用失败: {format_llm_error(exc)}，回退默认计划")

    fallback = default_plan("complex")
    fallback["source"] = "default_fallback"
    return fallback
