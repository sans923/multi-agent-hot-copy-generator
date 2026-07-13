"""
Judge 模型验证服务
==================
当规则验证结果不确定（软失败）时，调用独立 Judge 模型做目标对齐判断。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.utils.model_roles import get_model_for_role
from app.config import settings
from app.utils.llm_client import format_llm_error, get_deepseek_client
from app.utils.logger import logger

_JUDGE_SYSTEM = """你是文案质量 Judge，只判断「生成文案是否满足用户原始需求目标」。

规则：
1. 只输出 JSON：{"passed": true/false, "score": 0-100, "reason": "一句话"}
2. 不纠结格式细节，关注主题相关性与基本可用性
3. 明显跑题、空内容、完全无关 → passed=false
4. 风格略有偏差但主题相关 → passed=true, score>=70"""


def _parse_judge_json(raw: str) -> dict[str, Any] | None:
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
    if "passed" not in data:
        return None
    return {
        "passed": bool(data.get("passed")),
        "score": float(data.get("score") or 0),
        "reason": str(data.get("reason") or ""),
    }


def judge_goal_alignment(
    raw_requirement: str,
    copy_content: str,
    platform: str = "weibo",
) -> dict[str, Any]:
    """
    调用 Judge 模型判断文案是否满足用户原始目标。

    返回：
        {passed, score, reason, source: "judge"}
    """
    if not settings.ENABLE_JUDGE_VERIFY:
        return {
            "passed": False,
            "score": 0,
            "reason": "Judge 验证已关闭",
            "source": "judge_skipped",
        }

    if not copy_content or not raw_requirement:
        return {
            "passed": False,
            "score": 0,
            "reason": "文案或需求为空",
            "source": "judge",
        }

    user_prompt = (
        f"目标平台：{platform}\n\n"
        f"【用户原始需求】\n{raw_requirement}\n\n"
        f"【生成文案】\n{copy_content}\n\n"
        "请判断该文案是否满足用户需求，输出 JSON。"
    )

    try:
        client = get_deepseek_client()
        response = client.chat.completions.create(
            model=get_model_for_role("judge"),
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=512,
        )
        raw = response.choices[0].message.content or ""
        parsed = _parse_judge_json(raw)
        if not parsed:
            logger.warning("Judge 输出无法解析")
            return {
                "passed": False,
                "score": 0,
                "reason": "Judge 输出解析失败",
                "source": "judge",
            }

        result = {
            "passed": parsed["passed"],
            "score": parsed["score"],
            "reason": parsed["reason"],
            "source": "judge",
            "model": get_model_for_role("judge"),
        }
        logger.info(
            f"Judge 验证: passed={result['passed']}, score={result['score']}, "
            f"reason={result['reason'][:60]}"
        )
        return result

    except Exception as exc:
        logger.error(f"Judge 调用失败: {format_llm_error(exc)}")
        return {
            "passed": False,
            "score": 0,
            "reason": f"Judge 调用失败: {format_llm_error(exc)}",
            "source": "judge_error",
        }
