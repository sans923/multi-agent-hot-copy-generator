"""
写作规律提取服务
================
从优质长文中提取「抽象写作规律」（结构/节奏/手法），而非抄原文。

流程：去标识化 → 结构摘要 → LLM 结构化提取 → n-gram 防洗稿校验 → 多篇合并
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.utils.model_roles import get_model_for_role
from app.utils.llm_client import format_llm_error, get_deepseek_client
from app.utils.logger import logger

# 参考文中连续汉字超过此长度出现在 pattern 输出里视为洗稿风险
_NGRAM_OVERLAP_CHARS = 10

_PATTERN_JSON_SCHEMA_HINT = """
{
  "title_formula": {
    "pattern": "如 [数字] + [身份/场景] + [反差或结果]",
    "length_chars": "18-28",
    "must_include": ["数字或疑问"],
    "avoid": ["空洞形容词堆砌"]
  },
  "hook": {
    "type": "反常识|疑问式|故事式|痛点式|数字式",
    "beats": ["冲击句", "共情一句", "核心问题"],
    "first_screen_chars": 60
  },
  "structure": [
    {"section": "开篇", "function": "建立痛点与代入", "ratio": 0.1},
    {"section": "展开", "function": "案例+数据交叉论证", "ratio": 0.6},
    {"section": "升华", "function": "观点收束", "ratio": 0.2},
    {"section": "结尾", "function": "CTA", "ratio": 0.1}
  ],
  "rhythm": {
    "sentence_style": "短句为主",
    "paragraph_length": "2-4行/段",
    "subheadings": true,
    "emoji": false
  },
  "argument_mix": {"story": 0.3, "data": 0.4, "opinion": 0.3},
  "emotion_arc": ["焦虑", "共鸣", "希望", "行动"],
  "cta_pattern": "疑问式引导评论",
  "platform_fit": "头条长文",
  "confidence": 0.85
}
"""

_EXTRACT_SYSTEM_PROMPT = """你是「写作结构分析师」，不是改写员或摘抄员。

任务：从参考文章中提取可复用的写作规律，供另一篇全新主题文章使用。

硬性规则：
1. 禁止输出参考文中的原句、标题原文、可复制金句（连续 8 个以上汉字与原文相同视为违规）。
2. 只描述结构、节奏、手法、类型；用模板符号如 [数字]+[反差]+[悬念]。
3. 案例一律用类型描述：「个人经历型案例」「行业数据型论据」，不写具体故事细节。
4. 无法判断的字段填 "unknown"，不要编造。

只输出合法 JSON，不要 markdown 代码块。"""


def deidentify_text(text: str) -> str:
    """去标识化：弱化可逐字复制的专名与数字叙事。"""
    if not text:
        return ""
    result = text
    # 常见中文姓名（2-4 字）
    result = re.sub(r"[\u4e00-\u9fa5]{2,4}(?=说|表示|认为|透露)", "[人物A]", result)
    # 公司/机构后缀
    result = re.sub(
        r"[\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:公司|集团|科技|大学|研究院|部门)",
        "[机构X]",
        result,
    )
    # 手机号、邮箱
    result = re.sub(r"1[3-9]\d{9}", "[手机号]", result)
    result = re.sub(r"[\w.-]+@[\w.-]+\.\w+", "[邮箱]", result)
    # URL
    result = re.sub(r"https?://\S+", "[链接]", result)
    return result


def build_structure_summary(title: str, content: str, max_paragraphs: int = 8) -> str:
    """
    按段生成「功能摘要」（每段最多 80 字概述，禁止贴大段原文）。
    """
    paragraphs = [p.strip() for p in re.split(r"\n+", content) if p.strip()]
    if not paragraphs:
        paragraphs = [content[:500]]

    lines = [f"标题（已去标识）：{deidentify_text(title)}"]
    for i, para in enumerate(paragraphs[:max_paragraphs], start=1):
        cleaned = deidentify_text(para)
        preview = cleaned[:80] + ("…" if len(cleaned) > 80 else "")
        func = _guess_paragraph_function(i, len(paragraphs), para)
        lines.append(f"第{i}段（{func}）：{preview}")
    return "\n".join(lines)


def _guess_paragraph_function(index: int, total: int, text: str) -> str:
    """粗判段落职能（规则层，辅助 LLM）。"""
    if index == 1:
        return "开篇/钩子"
    if index == total:
        return "结尾/CTA"
    if re.search(r"[？?]", text[:30]):
        return "设问/转折"
    if re.search(r"\d+[%％万亿]|研究|数据|调查", text):
        return "数据/论据"
    if len(text) < 80:
        return "过渡/小结"
    return "展开/论证"


def _extract_json_from_response(text: str) -> dict[str, Any]:
    """从模型回复中解析 JSON。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


def has_ngram_overlap(pattern_text: str, source_texts: list[str], n: int = _NGRAM_OVERLAP_CHARS) -> bool:
    """检测 pattern 输出是否与参考文存在过长连续重叠（洗稿风险）。"""
    if not pattern_text or not source_texts or len(pattern_text) < n:
        return False
    combined = "".join(source_texts)
    for i in range(len(pattern_text) - n + 1):
        chunk = pattern_text[i : i + n]
        if chunk in combined:
            logger.warning(f"写作规律与参考文重叠片段: {chunk[:20]}...")
            return True
    return False


def extract_writing_pattern_from_articles(
    articles: list[dict[str, Any]],
    platform: str = "toutiao",
) -> dict[str, Any]:
    """
    从 1～3 篇长文提取并合并写作规律。

    参数 articles 每项需含：title, content, article_id（可选）, like_count（可选）
    """
    if not articles:
        return {"success": False, "error": "没有可参考的长文", "writing_pattern": None}

    articles = articles[:3]
    summaries: list[str] = []
    source_texts: list[str] = []

    for idx, art in enumerate(articles, start=1):
        title = art.get("title", "")
        content = art.get("content", "")
        if not content:
            continue
        source_texts.append(title + content)
        summary = build_structure_summary(title, content)
        like_count = art.get("like_count") or 0
        summaries.append(
            f"【参考文章 {idx}】article_id={art.get('article_id', '')} "
            f"互动量(点赞)={like_count}\n{summary}"
        )

    if not summaries:
        return {"success": False, "error": "参考长文正文为空", "writing_pattern": None}

    user_prompt = (
        f"目标平台：{platform}\n\n"
        + "\n\n".join(summaries)
        + f"\n\n请输出写作规律 JSON，结构参考：\n{_PATTERN_JSON_SCHEMA_HINT}"
    )

    try:
        client = get_deepseek_client()
        response = client.chat.completions.create(
            model=get_model_for_role("pattern"),
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
            max_tokens=2048,
        )
        raw = response.choices[0].message.content or ""
        pattern = _extract_json_from_response(raw)
    except Exception as exc:
        err = format_llm_error(exc)
        logger.error(f"extract_writing_pattern LLM 失败: {err}")
        return {"success": False, "error": f"规律提取失败: {err}", "writing_pattern": None}

    pattern_str = json.dumps(pattern, ensure_ascii=False)
    if has_ngram_overlap(pattern_str, source_texts):
        return {
            "success": False,
            "error": "提取结果与参考文重叠过多，已拒绝（防洗稿）",
            "writing_pattern": None,
        }

    pattern["source_article_ids"] = [
        str(a.get("article_id", "")) for a in articles if a.get("article_id")
    ]
    pattern["source_count"] = len(articles)
    pattern["platform_fit"] = pattern.get("platform_fit") or platform

    return {
        "success": True,
        "writing_pattern": pattern,
        "message": f"已从 {len(articles)} 篇长文提取抽象写作规律",
    }


def merge_writing_patterns(patterns: list[dict[str, Any]]) -> dict[str, Any]:
    """多篇 pattern 简单合并：hook.type / rhythm 取第一篇，structure 取最长。"""
    if not patterns:
        return {}
    if len(patterns) == 1:
        return patterns[0]

    merged = dict(patterns[0])
    hook_types = [p.get("hook", {}).get("type") for p in patterns if p.get("hook")]
    if hook_types:
        merged.setdefault("hook", {})["type"] = max(set(hook_types), key=hook_types.count)

    structures = [p.get("structure") for p in patterns if p.get("structure")]
    if structures:
        merged["structure"] = max(structures, key=len)

    merged["source_count"] = sum(p.get("source_count", 1) for p in patterns)
    return merged
