"""
任务分级服务
============
规则判定 simple / complex，简单任务走固定流水线，复杂任务走 Plan&Execute。
"""

from __future__ import annotations

import re
from typing import Any

from app.config import settings


def _extract_word_count_hint(text: str) -> int | None:
    """从需求文本解析「XXX字」字数要求。"""
    match = re.search(r"(\d{2,4})\s*字", text)
    if match:
        return int(match.group(1))
    return None


def classify_task(raw_requirement: str, platform: str = "weibo") -> dict[str, Any]:
    """
    规则分级（不调用 LLM，确定性、零成本）。

    返回：
        {
            "task_mode": "simple" | "complex",
            "reasons": [...],
            "estimated_word_count": int | None,
        }
    """
    text = (raw_requirement or "").strip()
    reasons: list[str] = []
    word_hint = _extract_word_count_hint(text)

    if word_hint and word_hint > settings.TASK_SIMPLE_MAX_WORDS:
        reasons.append(f"字数要求 {word_hint} 超过简单阈值 {settings.TASK_SIMPLE_MAX_WORDS}")

    if len(text) >= settings.TASK_COMPLEX_MIN_CHARS:
        reasons.append(f"需求描述长度 {len(text)} 超过 {settings.TASK_COMPLEX_MIN_CHARS} 字符")

    multi_platform_keywords = [
        "多平台",
        "多个平台",
        "全平台",
        "一稿多改",
        "A/B",
        "ab测试",
    ]
    for kw in multi_platform_keywords:
        if kw.lower() in text.lower():
            reasons.append(f"命中多平台/多版本关键词: {kw}")
            break

    platform_names = ["微博", "weibo", "小红书", "xiaohongshu", "头条", "toutiao", "抖音", "douyin"]
    mentioned = [p for p in platform_names if p.lower() in text.lower()]
    if len(set(mentioned)) >= 2:
        reasons.append(f"需求提及多个平台: {mentioned}")

    long_form_keywords = ["长文", "深度文", "1000字", "2000字", "3000字"]
    for kw in long_form_keywords:
        if kw in text:
            reasons.append(f"命中长文关键词: {kw}")
            break

    variant_keywords = ["两个版本", "2个版本", "多版本", "分别写"]
    for kw in variant_keywords:
        if kw in text:
            reasons.append(f"命中多版本关键词: {kw}")
            break

    task_mode = "complex" if reasons else "simple"
    return {
        "task_mode": task_mode,
        "reasons": reasons,
        "estimated_word_count": word_hint,
        "platform": platform,
    }
