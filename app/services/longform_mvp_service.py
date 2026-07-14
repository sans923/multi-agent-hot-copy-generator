"""今日头条长文 MVP 的结构化领域模型与可测试规则。

本模块刻意保持无数据库、无网络依赖：Agent 负责生成内容，这里负责规范阶段契约、
补齐安全默认值、保持章节顺序，并限制质量回路最多执行一次。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


TOUTIAO_MIN_WORDS = 1500
TOUTIAO_DEFAULT_WORDS = 2200
TOUTIAO_MAX_WORDS = 5000


class ContentBrief(BaseModel):
    topic: str
    platform: str = "toutiao"
    target_reader: str
    content_goal: str
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    reader_questions: list[str] = Field(default_factory=list)
    article_angle: str
    tone: str
    target_word_count: int
    hot_topics: list[str] = Field(default_factory=list)


class OutlineSection(BaseModel):
    id: str
    heading: str
    goal: str
    target_words: int
    reference_ids: list[str] = Field(default_factory=list)


class ArticleOutline(BaseModel):
    title_candidates: list[str]
    selected_title: str
    opening_strategy: str
    sections: list[OutlineSection]


class ArticleSection(BaseModel):
    id: str
    heading: str
    content: str


class QualityDimension(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)
    reason: str = ""


class FailedSection(BaseModel):
    section_id: str
    score: int = Field(ge=0, le=100)
    reason: str
    rewrite_instruction: str


class QualityReport(BaseModel):
    total_score: int = Field(ge=0, le=100)
    dimensions: list[QualityDimension] = Field(default_factory=list)
    failed_sections: list[FailedSection] = Field(default_factory=list)


class RewriteDecision(BaseModel):
    should_rewrite: bool
    next_rewrite_count: int
    sections: list[FailedSection] = Field(default_factory=list)
    reason: str


def build_content_brief(
    parsed_requirement: dict[str, Any],
    hot_topics: list[dict[str, Any]] | None = None,
) -> ContentBrief:
    """将现有 RequirementAgent 输出收敛成稳定的长文任务契约。"""
    platform = str(parsed_requirement.get("platform") or "toutiao").strip().lower()
    topic = str(parsed_requirement.get("topic") or "待分析主题").strip()
    style = str(parsed_requirement.get("style") or "理性、有共情、口语化").strip()

    raw_keywords = parsed_requirement.get("keywords") or []
    keywords = [str(item).strip() for item in raw_keywords if str(item).strip()]
    primary_keyword = keywords[0] if keywords else topic

    requested_words = _safe_int(parsed_requirement.get("word_count"), TOUTIAO_DEFAULT_WORDS)
    if platform == "toutiao":
        target_word_count = min(
            max(requested_words, TOUTIAO_MIN_WORDS),
            TOUTIAO_MAX_WORDS,
        )
    else:
        target_word_count = max(requested_words, 300)

    target_reader = str(
        parsed_requirement.get("target_reader")
        or parsed_requirement.get("audience")
        or f"关注“{topic}”并希望获得清晰判断与行动建议的读者"
    ).strip()
    content_goal = str(
        parsed_requirement.get("content_goal")
        or f"解释“{topic}”的关键问题，并给出可执行建议"
    ).strip()

    reader_questions = _clean_strings(parsed_requirement.get("reader_questions") or [])
    if len(reader_questions) < 3:
        defaults = [
            f"{topic}为什么值得现在关注？",
            f"{topic}对普通人会产生什么实际影响？",
            f"面对{topic}，接下来可以采取哪些行动？",
        ]
        reader_questions = _unique(reader_questions + defaults)[:5]

    hot_titles = _unique(
        str(item.get("title") or "").strip()
        for item in (hot_topics or [])
        if isinstance(item, dict) and item.get("title")
    )[:3]

    return ContentBrief(
        topic=topic,
        platform=platform,
        target_reader=target_reader,
        content_goal=content_goal,
        primary_keyword=primary_keyword,
        secondary_keywords=keywords[1:6],
        reader_questions=reader_questions,
        article_angle=str(
            parsed_requirement.get("article_angle")
            or "从具体场景切入，解释原因、影响与可执行方案"
        ).strip(),
        tone=style,
        target_word_count=target_word_count,
        hot_topics=hot_titles,
    )


def build_outline(
    brief: ContentBrief,
    raw_sections: list[dict[str, Any]] | None = None,
) -> ArticleOutline:
    """规范模型提纲；不足三节时自动补齐，保证 ID 唯一与字数预算可控。"""
    candidates: list[tuple[str, str, list[str]]] = []
    for raw in raw_sections or []:
        if not isinstance(raw, dict):
            continue
        heading = str(raw.get("heading") or raw.get("title") or "").strip()
        if not heading:
            continue
        goal = str(raw.get("goal") or raw.get("instruction") or "展开核心论点").strip()
        refs = _clean_strings(raw.get("reference_ids") or [])
        candidates.append((heading, goal, refs))

    defaults = [
        ("这件事为什么值得现在关注", brief.reader_questions[0], []),
        ("真正发生变化的三个关键环节", brief.reader_questions[1], []),
        ("普通人可以立即采取的行动", brief.reader_questions[2], []),
    ]
    existing_headings = {item[0] for item in candidates}
    for default in defaults:
        if len(candidates) >= 3:
            break
        if default[0] not in existing_headings:
            candidates.append(default)
            existing_headings.add(default[0])

    candidates = candidates[:8]
    section_count = len(candidates)
    body_budget = max(int(brief.target_word_count * 0.82), section_count * 200)
    words_per_section = max(body_budget // section_count, 200)

    sections = [
        OutlineSection(
            id=f"s{index}",
            heading=heading,
            goal=goal,
            target_words=words_per_section,
            reference_ids=reference_ids,
        )
        for index, (heading, goal, reference_ids) in enumerate(candidates, start=1)
    ]

    title_candidates = [
        brief.topic,
        f"{brief.topic}：真正需要看清的三件事",
        f"关于{brief.topic}，普通人最关心的问题终于讲清了",
    ]
    return ArticleOutline(
        title_candidates=title_candidates,
        selected_title=title_candidates[1],
        opening_strategy="具体场景或冲突切入，在前 150 字兑现标题承诺",
        sections=sections,
    )


def assemble_article(
    title: str,
    ordered_section_ids: list[str],
    sections: list[ArticleSection],
) -> str:
    """按照提纲顺序合并章节，忽略未知章节，避免并行生成导致顺序漂移。"""
    by_id = {section.id: section for section in sections}
    blocks = [f"# {title.strip()}"]
    for section_id in ordered_section_ids:
        section = by_id.get(section_id)
        if not section:
            continue
        blocks.append(f"## {section.heading.strip()}\n\n{section.content.strip()}")
    return "\n\n".join(blocks).strip()


def choose_sections_to_rewrite(
    report: QualityReport,
    threshold: int = 70,
    max_sections: int = 3,
) -> list[FailedSection]:
    """只选择真正低于阈值的章节，优先处理最低分，限制额外模型成本。"""
    failed = [item for item in report.failed_sections if item.score < threshold]
    failed.sort(key=lambda item: item.score)
    return failed[:max_sections]


def apply_rewrite_decision(
    report: QualityReport,
    rewrite_count: int,
    max_rewrites: int = 1,
    threshold: int = 70,
) -> RewriteDecision:
    """质量门禁：最多执行一次章节级改写，确保流程必然终止。"""
    current_count = max(rewrite_count, 0)
    sections = choose_sections_to_rewrite(report, threshold=threshold)
    can_rewrite = current_count < max_rewrites and bool(sections)
    if can_rewrite:
        return RewriteDecision(
            should_rewrite=True,
            next_rewrite_count=current_count + 1,
            sections=sections,
            reason="存在低分章节，执行一次定向重写",
        )
    reason = "已达到最大重写次数" if current_count >= max_rewrites else "没有低分章节"
    return RewriteDecision(
        should_rewrite=False,
        next_rewrite_count=current_count,
        sections=[],
        reason=reason,
    )


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_strings(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    return _unique(str(value).strip() for value in values if str(value).strip())


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

