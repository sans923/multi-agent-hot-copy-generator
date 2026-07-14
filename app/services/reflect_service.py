"""
Reflexion 反思服务（Agentic Phase 2）
======================================
步骤多次失败且 L1 重试耗尽后，由 Planner 模型分析失败原因并给出改写提示，
供 copywriter 在 L2 局部回退时参考（Bounded Reflexion，受 MAX_REFLECT_ROUNDS 限制）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.utils.llm_client import format_llm_error, get_deepseek_client
from app.utils.logger import logger
from app.utils.model_roles import get_model_for_role

_REFLECT_SYSTEM = """你是文案流水线 Reflexion Critic，只分析「当前步骤为何失败」并给出可执行的改写建议。

规则：
1. 只输出 JSON：
   {
     "summary": "一句话失败原因",
     "rewrite_hint": "给文案创作 Agent 的具体改写指令（50字内）",
     "focus": "topic|length|compliance|quality|structure 之一"
   }
2. 不要重写全文，只给策略性提示
3. 若验证未通过，优先指出与用户需求/平台规范的差距"""


def _parse_reflect_json(raw: str) -> dict[str, Any] | None:
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

    if not data.get("rewrite_hint") and not data.get("summary"):
        return None
    return {
        "summary": str(data.get("summary") or "步骤未通过验证，需要调整创作策略"),
        "rewrite_hint": str(data.get("rewrite_hint") or "请更紧扣用户主题并控制字数"),
        "focus": str(data.get("focus") or "quality"),
    }


def _fallback_reflection(stage: str, state: dict[str, Any]) -> dict[str, Any]:
    """LLM 不可用时的规则化反思（保证 L2 仍可回退）。"""
    verification = state.get("verification") or {}
    failed = verification.get("failed_checks") or []
    error = state.get("error") or verification.get("reason") or "步骤执行未达标"

    hint = "请重新创作：更紧扣用户主题，控制字数并避免敏感表达。"
    if "length_ok" in failed:
        hint = "请按用户字数要求重新创作，避免过短或过长。"
    elif "topic_match" in failed:
        hint = "请围绕用户原始需求主题重写，避免跑题。"
    elif stage == "copywriter":
        hint = "请重新检索规律并改写初稿，提升开头吸引力与平台语感。"

    return {
        "summary": str(error)[:120],
        "rewrite_hint": hint,
        "focus": "quality",
        "source": "rules",
    }


def reflect_on_step_failure(state: dict[str, Any], stage: str) -> dict[str, Any]:
    """
    对失败步骤做 Bounded Reflexion，返回改写提示。

    返回字段：
        summary, rewrite_hint, focus, source, context_append
    """
    raw_requirement = state.get("raw_requirement") or ""
    copy_content = (state.get("copy_content") or "")[:800]
    verification = state.get("verification") or {}
    step_def = {}
    plan = state.get("plan") or {}
    steps = plan.get("steps") or []
    idx = state.get("current_step") or 0
    if 0 <= idx < len(steps):
        step_def = steps[idx]

    user_prompt = (
        f"失败阶段：{stage}\n"
        f"步骤描述：{step_def.get('description') or step_def.get('step_id') or stage}\n"
        f"平台：{state.get('platform', 'weibo')}\n\n"
        f"【用户原始需求】\n{raw_requirement}\n\n"
        f"【当前初稿片段】\n{copy_content or '（尚无初稿）'}\n\n"
        f"【验证结果】\n{json.dumps(verification, ensure_ascii=False)[:600]}\n\n"
        f"【错误信息】\n{state.get('error') or '无'}\n\n"
        "请输出 JSON 反思结果。"
    )

    try:
        client = get_deepseek_client()
        response = client.chat.completions.create(
            model=get_model_for_role("planner"),
            messages=[
                {"role": "system", "content": _REFLECT_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=512,
        )
        raw = response.choices[0].message.content or ""
        parsed = _parse_reflect_json(raw)
        if not parsed:
            logger.warning("Reflexion 输出无法解析，使用规则回退")
            result = _fallback_reflection(stage, state)
        else:
            result = {**parsed, "source": "planner"}
            logger.info(
                f"Reflexion: stage={stage}, focus={result['focus']}, "
                f"hint={result['rewrite_hint'][:40]}"
            )
    except Exception as exc:
        logger.error(f"Reflexion 调用失败: {format_llm_error(exc)}")
        result = _fallback_reflection(stage, state)
        result["source"] = "rules_fallback"

    reflect_round = (state.get("reflect_count") or 0) + 1
    result["context_append"] = (
        f"[Reflexion 第{reflect_round}轮/{settings.MAX_REFLECT_ROUNDS}] "
        f"{result['rewrite_hint']}"
    )
    return result
