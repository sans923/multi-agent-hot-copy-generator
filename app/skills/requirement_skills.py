"""
需求与热榜相关 Skill（2个）
===========================
Skill 1: parse_requirement  - 解析用户原始需求，提取结构化信息
Skill 2: search_hotlist     - 搜索数据库中与需求相关的热榜话题

这两个 Skill 主要供【需求理解 Agent】使用：
用户说 "帮我写一篇关于AI的微博" ->
  parse_requirement 解析出 {topic: "AI", platform: "weibo", style: "..."}
  search_hotlist 找到近期 AI 相关热榜话题
  -> 两个结果合并，输出给文案创作 Agent
"""

import json
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from app.skills.base import BaseSkill
from app.models.hotlist_sync import HotlistSync
from app.utils.logger import logger


class ParseRequirementSkill(BaseSkill):
    """
    Skill 1: 解析用户需求
    
    这个 Skill 比较特殊：它本身不调用大模型（避免嵌套调用），
    而是用规则+关键词提取做基础解析，
    真正的语义理解由 Agent 的主 prompt 完成。
    
    主要作用：把用户的自由文本规范化为结构化数据，
    方便后续 Skill 使用（比如用 platform 查平台规则）
    """

    @property
    def name(self) -> str:
        return "parse_requirement"

    @property
    def description(self) -> str:
        return (
            "解析用户的文案需求，提取关键信息。"
            "当用户提供了原始需求描述时，优先调用此工具提取结构化信息，"
            "包括：主题、目标平台、写作风格、目标受众、关键词等。"
            "返回结构化的需求对象，供后续文案创作使用。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "raw_requirement": {
                    "type": "string",
                    "description": "用户原始需求描述文本"
                },
                "platform": {
                    "type": "string",
                    "description": "目标发布平台",
                    "enum": ["weibo", "wechat", "douyin", "xiaohongshu", "zhihu"],
                },
                "topic": {
                    "type": "string",
                    "description": "文案主题（如：AI技术、美食探店、旅游攻略）"
                },
                "style": {
                    "type": "string",
                    "description": "写作风格",
                    "enum": ["幽默", "严肃", "煽情", "专业", "口语化", "励志"]
                },
                "target_audience": {
                    "type": "string",
                    "description": "目标受众（如：年轻女性、职场人士、学生党）"
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "核心关键词列表，3-5个"
                },
                "word_count": {
                    "type": "integer",
                    "description": "期望字数，不传则根据平台自动决定"
                }
            },
            "required": ["raw_requirement", "platform", "topic"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        """
        解析需求 - 主要做数据规范化和补全
        
        注意：这里不调用大模型，因为调用方（需求理解Agent）
        已经是大模型了，它会填好这些参数再调用此Skill
        """
        raw_requirement = kwargs.get("raw_requirement", "")
        platform = kwargs.get("platform", "weibo")
        topic = kwargs.get("topic", "")
        style = kwargs.get("style", "口语化")
        target_audience = kwargs.get("target_audience", "普通用户")
        keywords = kwargs.get("keywords", [])
        word_count = kwargs.get("word_count")

        # 根据平台自动设置推荐字数
        platform_word_limits = {
            "weibo": 140,
            "xiaohongshu": 500,
            "wechat": 1000,
            "douyin": 100,
            "zhihu": 800,
        }

        if not word_count:
            word_count = platform_word_limits.get(platform, 300)

        # 构建结构化需求对象
        parsed = {
            "raw_requirement": raw_requirement,
            "platform": platform,
            "topic": topic,
            "style": style,
            "target_audience": target_audience,
            "keywords": keywords if keywords else [topic],
            "word_count": word_count,
            "platform_max_words": platform_word_limits.get(platform, 500),
        }

        logger.info(f"需求解析完成: topic={topic}, platform={platform}, style={style}")

        return {
            "success": True,
            "parsed_requirement": parsed,
            "message": f"需求解析完成，目标平台：{platform}，主题：{topic}，建议字数：{word_count}字"
        }


class SearchHotlistSkill(BaseSkill):
    """
    Skill 2: 搜索热榜话题
    
    从数据库的 hotlist_sync 表中，根据关键词搜索相关热榜话题
    为文案提供"蹭热度"的话题支撑
    
    搜索策略：
    1. 关键词精确匹配（title LIKE %keyword%）
    2. 按 fetched_at 倒序（越新越好）
    3. 过滤已过期数据（is_expired=0）
    """

    @property
    def name(self) -> str:
        return "search_hotlist"

    @property
    def description(self) -> str:
        return (
            "搜索与主题相关的热榜话题。"
            "当需要为文案找热点素材、蹭热度话题时调用。"
            "返回最新的相关热榜话题列表，包含话题标题、热度、平台来源。"
            "建议在生成文案之前调用，让文案结合当前热点。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "搜索关键词列表，会对每个关键词分别搜索"
                },
                "platform": {
                    "type": "string",
                    "description": "限定热榜来源平台，不传则搜索所有平台",
                    "enum": ["weibo", "douyin", "wechat", "bilibili", "zhihu", "all"]
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条数，默认5，最多10",
                    "default": 5
                }
            },
            "required": ["keywords"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        keywords: list[str] = kwargs.get("keywords", [])
        platform: str = kwargs.get("platform", "all")
        limit: int = min(kwargs.get("limit", 5), 10)

        if not keywords:
            return {"success": False, "error": "关键词不能为空", "hotlist": []}

        results = []
        seen_titles = set()  # 去重

        for keyword in keywords[:3]:  # 最多搜3个关键词，避免太慢
            query = db.query(HotlistSync).filter(
                HotlistSync.is_expired == 0,
                HotlistSync.title.like(f"%{keyword}%")
            )

            if platform and platform != "all":
                query = query.filter(HotlistSync.source_platform == platform)

            items = query.order_by(desc(HotlistSync.fetched_at)).limit(limit).all()

            for item in items:
                if item.title not in seen_titles:
                    seen_titles.add(item.title)
                    results.append({
                        "id": item.id,
                        "title": item.title,
                        "platform": item.source_platform,
                        "rank": item.rank,
                        "hot_value": item.hot_value,
                        "description": item.description or "",
                        "url": item.url or "",
                    })

        # 按热度（rank越小越热）排序
        results.sort(key=lambda x: x.get("rank") or 999)
        results = results[:limit]

        logger.info(f"热榜搜索: keywords={keywords}, 找到 {len(results)} 条")

        if not results:
            return {
                "success": True,
                "hotlist": [],
                "message": f"未找到与 {keywords} 相关的热榜话题，建议使用通用热点或自创话题"
            }

        return {
            "success": True,
            "hotlist": results,
            "message": f"找到 {len(results)} 条相关热榜话题"
        }
