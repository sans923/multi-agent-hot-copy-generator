"""
文案创作相关 Skill（4个）
=========================
Skill 5: generate_outline    - 生成文案大纲（结构框架）
Skill 6: write_copy_draft    - 根据大纲写文案正文
Skill 7: add_hashtags        - 为文案添加话题标签
Skill 8: save_final_copy     - 将完成的文案保存到数据库

这 4 个 Skill 主要供【文案创作 Agent】使用，形成一个创作流水线：
  generate_outline -> write_copy_draft -> add_hashtags -> save_final_copy

【为什么要拆成4步而不是一步生成？】
- 拆步骤让每步的 prompt 更专注，质量更高
- generate_outline 先定框架，write_copy_draft 再填内容，
  避免大模型发散，结构更清晰
- 方便审核 Agent 对每一步单独评审和修改
- 符合"单一职责原则"（每个函数只做一件事）
"""

import json
from datetime import datetime
from sqlalchemy.orm import Session

from app.skills.base import BaseSkill
from app.utils.logger import logger


class GenerateOutlineSkill(BaseSkill):
    """
    Skill 5: 生成文案大纲
    
    根据解析后的需求和热榜话题，生成文案的结构框架
    大纲确定了：开头钩子、主体段落、结尾召唤行动
    """

    @property
    def name(self) -> str:
        return "generate_outline"

    @property
    def description(self) -> str:
        return (
            "根据需求和热点话题生成文案大纲。"
            "在正式写文案之前调用，先确定文案结构：开头钩子、"
            "主体内容框架、结尾引导。"
            "返回结构化大纲，为后续写正文提供骨架。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "文案主题"
                },
                "platform": {
                    "type": "string",
                    "description": "目标发布平台"
                },
                "style": {
                    "type": "string",
                    "description": "写作风格"
                },
                "hot_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要蹭的热点话题标题列表"
                },
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "文案要包含的核心要点"
                },
                "hook_type": {
                    "type": "string",
                    "description": "开头钩子类型",
                    "enum": ["疑问式", "数字式", "反常识", "故事式", "痛点式"],
                    "default": "疑问式"
                },
                "writing_pattern": {
                    "type": "object",
                    "description": "由 extract_writing_pattern 或 get_style_card 返回的抽象写作规律 JSON"
                }
            },
            "required": ["topic", "platform", "style"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        topic = kwargs.get("topic", "")
        platform = kwargs.get("platform", "weibo")
        style = kwargs.get("style", "口语化")
        hot_topics = kwargs.get("hot_topics", [])
        key_points = kwargs.get("key_points", [])
        hook_type = kwargs.get("hook_type", "疑问式")
        writing_pattern = kwargs.get("writing_pattern")

        # 有抽象规律时优先按 pattern 生成大纲
        if writing_pattern and isinstance(writing_pattern, dict):
            outline = self._build_outline_from_pattern(
                topic=topic,
                platform=platform,
                style=style,
                hot_topics=hot_topics,
                key_points=key_points,
                writing_pattern=writing_pattern,
            )
        else:
            outline = self._build_outline(
                topic=topic,
                platform=platform,
                style=style,
                hot_topics=hot_topics,
                key_points=key_points,
                hook_type=hook_type,
            )

        logger.info(f"生成文案大纲: topic={topic}, platform={platform}, pattern={bool(writing_pattern)}")

        return {
            "success": True,
            "outline": outline,
            "message": f"文案大纲生成完成，共 {len(outline['sections'])} 个段落"
        }

    def _build_outline_from_pattern(
        self,
        topic: str,
        platform: str,
        style: str,
        hot_topics: list,
        key_points: list,
        writing_pattern: dict,
    ) -> dict:
        """根据抽象写作规律动态生成大纲段落。"""
        hook = writing_pattern.get("hook", {}) or {}
        hook_type = hook.get("type", "疑问式")
        title_formula = writing_pattern.get("title_formula", {}) or {}
        structure = writing_pattern.get("structure") or []
        rhythm = writing_pattern.get("rhythm", {}) or {}
        cta_pattern = writing_pattern.get("cta_pattern", "引导互动")
        emotion_arc = writing_pattern.get("emotion_arc") or []

        sections = []
        if title_formula.get("pattern"):
            sections.append({
                "name": "标题",
                "type": "title",
                "instruction": f"按公式撰写：{title_formula.get('pattern')}；长度 {title_formula.get('length_chars', '适中')}",
                "must_include": title_formula.get("must_include", []),
                "avoid": title_formula.get("avoid", []),
            })

        beats = hook.get("beats") or ["冲击句", "共情", "核心问题"]
        sections.append({
            "name": "开头钩子",
            "type": "hook",
            "hook_type": hook_type,
            "instruction": f"钩子类型：{hook_type}；节奏：{' → '.join(beats)}",
            "hot_topic": hot_topics[0] if hot_topics else None,
            "first_screen_chars": hook.get("first_screen_chars", 60),
        })

        if structure:
            for block in structure:
                ratio = block.get("ratio", 0)
                word_hint = f"约占全文 {int(float(ratio) * 100)}%" if ratio else ""
                sections.append({
                    "name": block.get("section", "段落"),
                    "type": "body",
                    "instruction": f"{block.get('function', '展开论证')} {word_hint}".strip(),
                    "key_points": key_points[:3] if key_points else [],
                })
        else:
            sections.append({
                "name": "核心内容",
                "type": "body",
                "instruction": "按爆款长文节奏展开，短句+小结",
                "key_points": key_points[:3],
            })

        sections.append({
            "name": "结尾互动",
            "type": "cta",
            "instruction": f"CTA 模式：{cta_pattern}",
        })

        return {
            "topic": topic,
            "platform": platform,
            "style": style,
            "sections": sections,
            "hot_topics_to_use": hot_topics[:2],
            "total_sections": len(sections),
            "writing_pattern_applied": True,
            "rhythm_hints": rhythm,
            "emotion_arc": emotion_arc,
            "title_formula": title_formula.get("pattern", ""),
        }

    def _build_outline(self, topic, platform, style, hot_topics, key_points, hook_type) -> dict:
        """构建文案大纲框架"""

        # 不同平台的大纲结构不同
        if platform in ["weibo", "douyin"]:
            sections = [
                {
                    "name": "开头钩子",
                    "type": "hook",
                    "hook_type": hook_type,
                    "instruction": f"用{hook_type}开头，前20字必须抓住注意力",
                    "hot_topic": hot_topics[0] if hot_topics else None,
                },
                {
                    "name": "核心内容",
                    "type": "body",
                    "instruction": "简洁有力地传递核心信息，每句话都要推进",
                    "key_points": key_points[:3],
                },
                {
                    "name": "结尾互动",
                    "type": "cta",
                    "instruction": "引导互动，可以是疑问/投票/求扩散",
                },
            ]
        elif platform == "xiaohongshu":
            sections = [
                {
                    "name": "标题",
                    "type": "title",
                    "instruction": "10-20字，包含数字或疑问，放Emoji",
                },
                {
                    "name": "开头引入",
                    "type": "hook",
                    "hook_type": hook_type,
                    "instruction": "个人化场景引入，建立代入感",
                    "hot_topic": hot_topics[0] if hot_topics else None,
                },
                {
                    "name": "干货主体",
                    "type": "body",
                    "instruction": "分点阐述，每点前放Emoji，具体可操作",
                    "key_points": key_points,
                },
                {
                    "name": "个人总结",
                    "type": "summary",
                    "instruction": "真实感受/体验，增加可信度",
                },
                {
                    "name": "结尾引导",
                    "type": "cta",
                    "instruction": "引导收藏/关注，如'收藏这篇不迷路！'",
                },
            ]
        else:  # wechat / zhihu
            sections = [
                {
                    "name": "标题",
                    "type": "title",
                    "instruction": "数字+场景+结果的标题公式",
                },
                {
                    "name": "引言",
                    "type": "intro",
                    "instruction": "150字内给读者继续读的理由",
                    "hot_topic": hot_topics[0] if hot_topics else None,
                },
                {
                    "name": f"主体段落（共{max(len(key_points), 3)}段）",
                    "type": "body",
                    "instruction": "每段有小标题，200字内，有数据/案例支撑",
                    "key_points": key_points,
                },
                {
                    "name": "结尾总结",
                    "type": "conclusion",
                    "instruction": "总结核心观点，引导分享/在看",
                },
            ]

        return {
            "topic": topic,
            "platform": platform,
            "style": style,
            "sections": sections,
            "hot_topics_to_use": hot_topics[:2],
            "total_sections": len(sections),
        }


class WriteCopyDraftSkill(BaseSkill):
    """
    Skill 6: 根据大纲写文案正文
    
    这个 Skill 是"脚手架"式的：
    它把大纲的每个段落信息整理成一个清晰的写作指令，
    由 Agent（大模型）根据这个指令生成实际文案内容
    
    注意：这个 Skill 本身不调用大模型，
    它负责把大纲+需求整合成最优的写作 prompt，
    Agent 收到 Skill 返回后，根据这些指令去生成文案
    """

    @property
    def name(self) -> str:
        return "write_copy_draft"

    @property
    def description(self) -> str:
        return (
            "根据文案大纲生成完整的文案初稿。"
            "需要先调用 generate_outline 获取大纲，再调用此工具。"
            "传入大纲、平台规则、参考文案，生成符合平台规范的完整文案。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "outline": {
                    "type": "object",
                    "description": "由 generate_outline 生成的大纲对象"
                },
                "platform_rules": {
                    "type": "object",
                    "description": "由 get_platform_rules 获取的平台规则"
                },
                "similar_copies": {
                    "type": "array",
                    "description": "参考的相似历史文案列表",
                    "items": {"type": "object"}
                },
                "hot_titles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要融入文案的热榜话题标题"
                },
                "extra_requirements": {
                    "type": "string",
                    "description": "额外的特殊要求（如：强调某个产品功能，避免某个词）"
                },
                "writing_pattern": {
                    "type": "object",
                    "description": "抽象写作规律，约束语气与节奏，禁止照搬参考原文"
                }
            },
            "required": ["outline"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        outline = kwargs.get("outline", {})
        platform_rules = kwargs.get("platform_rules", {})
        similar_copies = kwargs.get("similar_copies", [])
        hot_titles = kwargs.get("hot_titles", [])
        extra_requirements = kwargs.get("extra_requirements", "")
        writing_pattern = kwargs.get("writing_pattern")

        if not outline:
            return {"success": False, "error": "大纲不能为空，请先调用 generate_outline"}

        # 构建写作指令（这些指令会被 Agent 用来生成文案）
        writing_brief = self._build_writing_brief(
            outline=outline,
            platform_rules=platform_rules,
            similar_copies=similar_copies,
            hot_titles=hot_titles,
            extra_requirements=extra_requirements,
            writing_pattern=writing_pattern,
        )

        logger.info(f"写作摘要生成完成: platform={outline.get('platform')}")

        return {
            "success": True,
            "writing_brief": writing_brief,
            "instruction": (
                "请根据上面的写作摘要，现在开始创作完整文案。"
                "严格按照大纲结构与 writing_pattern 的节奏展开，融入热点话题，"
                f"控制在{outline.get('platform', '')}平台推荐字数范围内。"
                "禁止照搬任何参考长文原句，只学习抽象结构与手法。"
                "直接输出文案正文，不需要解释。"
            )
        }

    def _build_writing_brief(
        self, outline, platform_rules, similar_copies, hot_titles, extra_requirements,
        writing_pattern=None,
    ) -> dict:
        """整合所有创作素材为写作摘要"""

        brief = {
            "topic": outline.get("topic", ""),
            "platform": outline.get("platform", ""),
            "style": outline.get("style", ""),
            "structure": outline.get("sections", []),
            "word_limit": platform_rules.get("recommended_words", "300字以内") if platform_rules else "300字以内",
            "hashtag_format": platform_rules.get("hashtag_format", "") if platform_rules else "",
            "style_tips": platform_rules.get("style_tips", [])[:3] if platform_rules else [],
        }

        if hot_titles:
            brief["hot_topics_to_mention"] = hot_titles[:2]

        if similar_copies:
            brief["reference_copies"] = [
                {
                    "content": c.get("content", "")[:100],  # 只取前100字作参考
                    "score": c.get("review_score", 0),
                }
                for c in similar_copies[:2]
            ]

        if extra_requirements:
            brief["extra_requirements"] = extra_requirements

        if writing_pattern and isinstance(writing_pattern, dict):
            # 只注入抽象规律，不注入参考全文
            brief["writing_pattern"] = {
                "title_formula": (writing_pattern.get("title_formula") or {}).get("pattern"),
                "hook_type": (writing_pattern.get("hook") or {}).get("type"),
                "rhythm": writing_pattern.get("rhythm"),
                "emotion_arc": writing_pattern.get("emotion_arc"),
                "cta_pattern": writing_pattern.get("cta_pattern"),
                "argument_mix": writing_pattern.get("argument_mix"),
            }
            brief["anti_plagiarism"] = "禁止复制参考长文原句，仅按结构与节奏创作"

        return brief


class AddHashtagsSkill(BaseSkill):
    """
    Skill 7: 为文案添加话题标签
    
    根据文案内容、平台规则、热榜话题，
    智能推荐最合适的话题标签
    """

    @property
    def name(self) -> str:
        return "add_hashtags"

    @property
    def description(self) -> str:
        return (
            "为生成的文案添加合适的话题标签（Hashtags）。"
            "根据文案内容、目标平台和热榜话题，推荐最能提升曝光的标签。"
            "在文案正文完成后调用，优化文案的话题标签。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "copy_content": {
                    "type": "string",
                    "description": "文案正文内容"
                },
                "platform": {
                    "type": "string",
                    "description": "目标平台"
                },
                "topic": {
                    "type": "string",
                    "description": "文案主题"
                },
                "hot_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "相关热榜话题标题，优先加入"
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "核心关键词"
                }
            },
            "required": ["copy_content", "platform", "topic"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        copy_content = kwargs.get("copy_content", "")
        platform = kwargs.get("platform", "weibo")
        topic = kwargs.get("topic", "")
        hot_topics = kwargs.get("hot_topics", [])
        keywords = kwargs.get("keywords", [])

        hashtags = self._generate_hashtags(
            platform=platform,
            topic=topic,
            hot_topics=hot_topics,
            keywords=keywords,
        )

        # 格式化标签
        formatted = self._format_hashtags(hashtags, platform)

        logger.info(f"生成话题标签: platform={platform}, count={len(hashtags)}")

        return {
            "success": True,
            "hashtags": hashtags,
            "formatted_hashtags": formatted,
            "message": f"生成了 {len(hashtags)} 个话题标签"
        }

    def _generate_hashtags(self, platform, topic, hot_topics, keywords) -> list[str]:
        """生成话题标签列表"""
        tags = []

        # 1. 优先加入热榜话题（最有流量）
        for ht in hot_topics[:2]:
            clean = ht.replace("#", "").strip()
            if clean and len(clean) <= 20:
                tags.append(clean)

        # 2. 加入主题标签
        if topic:
            tags.append(topic)

        # 3. 加入关键词标签
        for kw in keywords[:3]:
            if kw not in tags:
                tags.append(kw)

        # 4. 根据平台限制数量
        platform_limits = {
            "weibo": 3,
            "xiaohongshu": 8,
            "douyin": 5,
            "wechat": 0,  # 公众号一般不用话题标签
            "zhihu": 0,
        }
        limit = platform_limits.get(platform, 5)

        return tags[:limit] if limit > 0 else []

    def _format_hashtags(self, hashtags: list[str], platform: str) -> str:
        """按平台格式化话题标签"""
        if not hashtags:
            return ""

        if platform == "weibo":
            return " ".join(f"#{tag}#" for tag in hashtags)
        elif platform in ["xiaohongshu", "douyin"]:
            return " ".join(f"#{tag}" for tag in hashtags)
        else:
            return ""


class SaveFinalCopySkill(BaseSkill):
    """
    Skill 8: 保存最终文案到数据库
    
    文案经过创作 + 审核优化后，调用此 Skill 持久化保存
    同时触发向量化，存入 ChromaDB 供后续 RAG 检索
    """

    @property
    def name(self) -> str:
        return "save_final_copy"

    @property
    def description(self) -> str:
        return (
            "将完成的文案保存到数据库。"
            "当文案创作完成（或审核优化完成后），调用此工具持久化保存。"
            "保存成功后文案将进入历史文案库，可被后续 RAG 检索参考。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "所属任务ID"
                },
                "title": {
                    "type": "string",
                    "description": "文案标题"
                },
                "content": {
                    "type": "string",
                    "description": "文案正文内容"
                },
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "话题标签列表"
                },
                "platform": {
                    "type": "string",
                    "description": "目标平台"
                },
                "tone": {
                    "type": "string",
                    "description": "文案风格/语气"
                },
                "hot_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "关联的热榜关键词"
                },
                "version": {
                    "type": "integer",
                    "description": "版本号：1=初稿，2=优化稿",
                    "default": 1
                },
                "is_final": {
                    "type": "boolean",
                    "description": "是否是最终版本",
                    "default": False
                },
                "tokens_used": {
                    "type": "integer",
                    "description": "生成本文案消耗的token数",
                    "default": 0
                }
            },
            "required": ["task_id", "content", "platform"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        from app.models.copy import Copy

        task_id = kwargs.get("task_id")
        title = kwargs.get("title", "")
        content = kwargs.get("content", "")
        hashtags = kwargs.get("hashtags", [])
        platform = kwargs.get("platform", "weibo")
        tone = kwargs.get("tone", "")
        hot_keywords = kwargs.get("hot_keywords", [])
        version = kwargs.get("version", 1)
        is_final = kwargs.get("is_final", False)
        tokens_used = kwargs.get("tokens_used", 0)

        if not content:
            return {"success": False, "error": "文案内容不能为空"}

        if not task_id:
            return {"success": False, "error": "task_id 不能为空"}

        # 创建文案记录
        copy = Copy(
            task_id=task_id,
            title=title,
            content=content,
            hashtags=hashtags,
            platform=platform,
            tone=tone,
            hot_keywords=hot_keywords,
            version=version,
            is_final=is_final,
            tokens_used=tokens_used,
        )

        db.add(copy)
        db.commit()
        db.refresh(copy)

        logger.info(f"文案已保存: copy_id={copy.id}, task_id={task_id}, version={version}")

        #trae 将文案向量化后存入 ChromaDB，供后续 RAG 检索使用
        from app.services.embedding_service import upsert_copy_to_chroma
        upsert_copy_to_chroma(
            copy_id=copy.id,
            task_id=task_id,
            content=content,
            platform=platform,
            tone=tone,
            version=version,
            is_final=is_final,
            hot_keywords=hot_keywords,
        )

        return {
            "success": True,
            "copy_id": copy.id,
            "task_id": task_id,
            "version": version,
            "message": f"文案已保存，copy_id={copy.id}"
        }