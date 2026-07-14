"""今日头条长文 MVP 的领域规则测试。

用户旅程：作为内容创作者，我希望系统先规划再分节写作，并且只重写低分章节，
从而在可控成本内得到结构完整、过程可解释的长文。
"""

from app.services.longform_mvp_service import (
    ArticleSection,
    QualityDimension,
    QualityReport,
    apply_rewrite_decision,
    assemble_article,
    build_content_brief,
    build_outline,
    choose_sections_to_rewrite,
)


def test_toutiao_brief_defaults_to_longform_word_count():
    brief = build_content_brief(
        parsed_requirement={
            "topic": "35 岁程序员失业后怎么办",
            "platform": "toutiao",
            "style": "理性、有共情",
            "keywords": ["程序员失业", "职业转型"],
            "word_count": 300,
        },
        hot_topics=[{"title": "中年职场人的第二增长曲线"}],
    )

    assert brief.platform == "toutiao"
    assert brief.target_word_count >= 1500
    assert brief.target_reader
    assert brief.content_goal
    assert brief.primary_keyword == "程序员失业"


def test_outline_has_unique_section_ids_and_at_least_three_body_sections():
    brief = build_content_brief(
        parsed_requirement={
            "topic": "AI 如何改变普通人的工作",
            "platform": "toutiao",
            "keywords": ["AI 就业"],
            "word_count": 2000,
        },
        hot_topics=[],
    )

    outline = build_outline(
        brief,
        raw_sections=[
            {"heading": "变化已经发生", "goal": "用场景解释变化"},
            {"heading": "哪些岗位先受影响", "goal": "分析岗位差异"},
        ],
    )

    assert len(outline.sections) >= 3
    assert len({section.id for section in outline.sections}) == len(outline.sections)
    assert all(section.target_words > 0 for section in outline.sections)
    assert sum(section.target_words for section in outline.sections) <= brief.target_word_count


def test_assemble_article_preserves_outline_order():
    sections = [
        ArticleSection(id="s2", heading="第二节", content="第二节正文"),
        ArticleSection(id="s1", heading="第一节", content="第一节正文"),
    ]

    article = assemble_article(
        title="测试标题",
        ordered_section_ids=["s1", "s2"],
        sections=sections,
    )

    assert article.index("第一节") < article.index("第二节")
    assert article.startswith("# 测试标题")


def test_only_low_score_sections_are_selected_for_rewrite():
    report = QualityReport(
        total_score=74,
        dimensions=[
            QualityDimension(name="结构完整性", score=82, reason="结构完整"),
            QualityDimension(name="信息密度", score=58, reason="第三节过于笼统"),
        ],
        failed_sections=[
            {
                "section_id": "s3",
                "score": 55,
                "reason": "缺少案例",
                "rewrite_instruction": "增加具体案例和行动建议",
            },
            {
                "section_id": "s2",
                "score": 83,
                "reason": "已经达标",
                "rewrite_instruction": "无需修改",
            },
        ],
    )

    selected = choose_sections_to_rewrite(report, threshold=70)

    assert [item.section_id for item in selected] == ["s3"]


def test_rewrite_decision_allows_only_one_iteration():
    report = QualityReport(
        total_score=62,
        dimensions=[],
        failed_sections=[
            {
                "section_id": "s1",
                "score": 50,
                "reason": "开头缺少吸引力",
                "rewrite_instruction": "使用具体冲突场景开头",
            }
        ],
    )

    first = apply_rewrite_decision(report, rewrite_count=0, max_rewrites=1)
    second = apply_rewrite_decision(report, rewrite_count=1, max_rewrites=1)

    assert first.should_rewrite is True
    assert first.next_rewrite_count == 1
    assert second.should_rewrite is False
    assert second.next_rewrite_count == 1
