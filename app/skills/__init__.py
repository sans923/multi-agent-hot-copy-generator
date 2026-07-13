"""
Skills 包 - 10 个 Skill + 注册器工厂
======================================
这个 __init__.py 负责把所有 Skill 注册到一个全局注册器中，
供 Agent 按需获取工具列表

【10 个 Skill 清单】
需求理解类（供需求理解Agent使用）：
  1. parse_requirement    - 解析用户原始需求为结构化数据
  2. search_hotlist       - 搜索相关热榜话题

平台规则类（供文案创作Agent使用）：
  3. get_platform_rules   - 获取目标平台文案规范

RAG检索类（供文案创作Agent使用）：
  4. search_similar_copies - 从向量库检索相似历史文案

文案创作类（供文案创作Agent使用）：
  5. generate_outline     - 生成文案大纲（结构框架）
  6. write_copy_draft     - 根据大纲生成完整文案
  7. add_hashtags         - 生成并添加话题标签
  8. save_final_copy      - 保存文案到数据库

审核优化类（供审核优化Agent使用）：
  9. review_copy_quality  - 多维度评审文案质量（0-100分）
  10. optimize_copy       - 根据审核意见优化文案
"""

from app.skills.base import BaseSkill, SkillRegistry, SkillExecutor
from app.skills.skill_response import skill_ok, skill_fail, normalize_skill_result
from app.skills.requirement_skills import ParseRequirementSkill, SearchHotlistSkill
from app.skills.platform_skills import GetPlatformRulesSkill
from app.skills.rag_skills import SearchSimilarCopiesSkill
from app.skills.copy_skills import (
    GenerateOutlineSkill,
    WriteCopyDraftSkill,
    AddHashtagsSkill,
    SaveFinalCopySkill,
)
from app.skills.review_skills import ReviewCopyQualitySkill, OptimizeCopySkill
from app.skills.toutiao_rag_skills import SearchToutiaoReferencesSkill
from app.skills.style_skills import (
    SearchHotArticlesByTopicSkill,
    ExtractWritingPatternSkill,
    GetStyleCardSkill,
    SaveStyleCardSkill,
)
from app.skills.compliance_skills import (
    CheckSensitiveWordsSkill,
    CheckPlagiarismOverlapSkill,
)


def create_skill_registry() -> SkillRegistry:
    """
    创建并返回注册了所有 10 个 Skill 的注册器
    
    在 Agent 初始化时调用：
        registry = create_skill_registry()
        executor = SkillExecutor(registry)
        tools = registry.get_tools_by_names(REQUIREMENT_AGENT_SKILLS)
    """
    registry = SkillRegistry()

    from app.skills.delegation_skills import (
        DelegateToRequirementSkill,
        DelegateToCopywriterSkill,
        DelegateToReviewerSkill,
        FinishTaskSkill,
    )

    # 注册全部 Skill
    (registry
        .register(ParseRequirementSkill())
        .register(SearchHotlistSkill())
        .register(GetPlatformRulesSkill())
        .register(SearchSimilarCopiesSkill())
        .register(GenerateOutlineSkill())
        .register(WriteCopyDraftSkill())
        .register(AddHashtagsSkill())
        .register(SaveFinalCopySkill())
        .register(ReviewCopyQualitySkill())
        .register(OptimizeCopySkill())
        .register(SearchToutiaoReferencesSkill())
        .register(SearchHotArticlesByTopicSkill())
        .register(ExtractWritingPatternSkill())
        .register(GetStyleCardSkill())
        .register(SaveStyleCardSkill())
        .register(CheckSensitiveWordsSkill())
        .register(CheckPlagiarismOverlapSkill())
        .register(DelegateToRequirementSkill())
        .register(DelegateToCopywriterSkill())
        .register(DelegateToReviewerSkill())
        .register(FinishTaskSkill())
    )

    from app.utils.logger import logger
    logger.info(f"Skill 注册完成，共 {len(registry)} 个: {registry.list_skills()}")

    return registry


# 各 Agent 使用的 Skill 子集（按职责划分）
REQUIREMENT_AGENT_SKILLS = [
    "parse_requirement",
    "search_hotlist",
]

COPYWRITER_AGENT_SKILLS = [
    "get_platform_rules",
    "get_style_card",
    "search_hot_articles_by_topic",
    "extract_writing_pattern",
    "search_toutiao_references",
    "search_similar_copies",
    "generate_outline",
    "write_copy_draft",
    "add_hashtags",
    "save_final_copy",
]

REVIEWER_AGENT_SKILLS = [
    "check_sensitive_words",
    "check_plagiarism_overlap",
    "review_copy_quality",
    "optimize_copy",
    "save_final_copy",
]

LEAD_AGENT_SKILLS = [
    "delegate_to_requirement",
    "delegate_to_copywriter",
    "delegate_to_reviewer",
    "finish_task",
]


# 全局单例注册器（模块加载时创建一次）
_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """获取全局注册器单例（懒加载）"""
    global _registry
    if _registry is None:
        _registry = create_skill_registry()
    return _registry


def get_skill_executor() -> SkillExecutor:
    """获取全局执行器（每次创建新实例，共享注册器）"""
    return SkillExecutor(get_skill_registry())


__all__ = [
    "BaseSkill",
    "SkillRegistry",
    "SkillExecutor",
    "create_skill_registry",
    "get_skill_registry",
    "get_skill_executor",
    "skill_ok",
    "skill_fail",
    "normalize_skill_result",
    "REQUIREMENT_AGENT_SKILLS",
    "COPYWRITER_AGENT_SKILLS",
    "REVIEWER_AGENT_SKILLS",
    "LEAD_AGENT_SKILLS",
]
