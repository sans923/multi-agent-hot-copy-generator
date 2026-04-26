"""
平台规则 Skill（1个）
=====================
Skill 3: get_platform_rules - 获取目标平台的文案规则

每个平台的规则差异很大：
- 微博：140字限制，话题标签 #话题#，适合简短有力
- 小红书：可以很长，Emoji多，"宝藏/绝了/测评"词汇常见
- 抖音：要"钩子"开头，节奏快，口语化
- 微信：排版讲究，小标题分段，适合长文
- 知乎：强调专业性，有理有据，结构化

【为什么要把这个做成 Skill 而不是写死在 prompt 里？】
1. 方便扩展：以后加新平台只需修改这一个地方
2. Agent 可以按需查询，不需要把所有平台规则都塞进 context（节省 token）
3. 规则可以随时更新，不需要改 Agent 代码
"""

from sqlalchemy.orm import Session
from app.skills.base import BaseSkill
from app.utils.logger import logger


# 平台规则配置（实际项目可以存数据库，这里先用字典）
PLATFORM_RULES = {
    "weibo": {
        "name": "微博",
        "max_words": 140,
        "recommended_words": "100-140",
        "hashtag_format": "#话题#",
        "hashtag_count": "2-3个",
        "style_tips": [
            "开头要抓眼球，前20字决定是否被展开",
            "适当使用表情符号，但不要超过5个",
            "结尾加互动引导：你怎么看？欢迎评论",
            "话题标签放开头或结尾",
            "多用短句，避免长难句",
        ],
        "forbidden_words": ["广告", "推广", "优惠码"],
        "best_post_time": "早7-9点、午12-14点、晚20-23点",
        "engagement_tips": "提问式结尾互动率最高，如'你有这种经历吗？'",
    },
    "xiaohongshu": {
        "name": "小红书",
        "max_words": 1000,
        "recommended_words": "300-600",
        "hashtag_format": "#话题",
        "hashtag_count": "3-8个",
        "style_tips": [
            "标题用数字或疑问句，如'5个方法让你...'",
            "大量使用Emoji，每段开头放Emoji",
            "用'姐妹/宝子/绝绝子/yyds'等小红书专属词汇",
            "个人真实体验感强，第一人称叙述",
            "干货清单形式最受欢迎：步骤式/对比式/推荐式",
            "结尾引导收藏：'收藏这篇不迷路！'",
        ],
        "forbidden_words": ["代购", "私信", "加微信", "淘宝链接"],
        "best_post_time": "早7-8点、午11-12点、晚21-23点",
        "engagement_tips": "封面图文案+正文双层钩子，封面决定点击率",
    },
    "douyin": {
        "name": "抖音",
        "max_words": 150,
        "recommended_words": "50-100",
        "hashtag_format": "#话题",
        "hashtag_count": "3-5个",
        "style_tips": [
            "前3秒必须有钩子：直接说结论或反常识",
            "用口语化语言，像在说话不像在写文章",
            "节奏要快，每句话要推进",
            "善用反转：先给出错误认知，再揭晓真相",
            "结尾要call to action：点赞/关注/评论区说",
        ],
        "forbidden_words": ["点击购买", "扫码", "私信我"],
        "best_post_time": "早6-8点、午12-14点、晚19-22点",
        "engagement_tips": "评论区互动话题设计比正文更重要",
    },
    "wechat": {
        "name": "微信公众号",
        "max_words": 5000,
        "recommended_words": "800-2000",
        "hashtag_format": "无话题标签",
        "hashtag_count": "无需",
        "style_tips": [
            "标题黄金公式：数字+场景+结果（'3步搞定...'）",
            "开头150字内要给读者'继续读'的理由",
            "用小标题分段，每段200字内",
            "多用列表、加粗提高可读性",
            "故事+干货结构最受欢迎",
            "结尾引导分享+在看",
        ],
        "forbidden_words": ["转发", "朋友圈", "外链"],
        "best_post_time": "晚20-22点发布打开率最高",
        "engagement_tips": "在看数影响推荐，结尾要引导读者点在看",
    },
    "zhihu": {
        "name": "知乎",
        "max_words": 10000,
        "recommended_words": "500-2000",
        "hashtag_format": "无话题标签（用话题区）",
        "hashtag_count": "无需",
        "style_tips": [
            "开头要有权威感：先亮背景或结论",
            "有理有据：数据/案例/逻辑缺一不可",
            "结构清晰：总-分-总",
            "用'我的亲身经历'增加可信度",
            "避免绝对化表述，用'通常/一般/大多数情况'",
            "适当引用权威来源",
        ],
        "forbidden_words": ["绝对/肯定/一定（谨慎使用）", "广告"],
        "best_post_time": "下午15-17点、晚20-22点",
        "engagement_tips": "高赞回答都有个人独特视角，避免人云亦云",
    },
}


class GetPlatformRulesSkill(BaseSkill):
    """
    Skill 3: 获取平台文案规则
    
    文案创作 Agent 在生成文案前调用此 Skill，
    了解目标平台的字数、格式、风格要求，
    确保生成的文案符合平台规范
    """

    @property
    def name(self) -> str:
        return "get_platform_rules"

    @property
    def description(self) -> str:
        return (
            "获取指定平台的文案创作规则和最佳实践。"
            "在创作文案之前必须调用，了解平台的字数限制、"
            "话题标签格式、写作风格要求、禁用词等规范，"
            "确保生成的文案符合平台特性。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "目标发布平台",
                    "enum": ["weibo", "wechat", "douyin", "xiaohongshu", "zhihu"]
                }
            },
            "required": ["platform"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        platform = kwargs.get("platform", "weibo")

        rules = PLATFORM_RULES.get(platform)
        if not rules:
            return {
                "success": False,
                "error": f"未找到平台 '{platform}' 的规则，支持的平台：{list(PLATFORM_RULES.keys())}"
            }

        logger.info(f"获取平台规则: {platform}")

        return {
            "success": True,
            "platform": platform,
            "rules": rules,
            "summary": (
                f"【{rules['name']}创作规范】"
                f"建议字数：{rules['recommended_words']}字，"
                f"话题标签：{rules['hashtag_format']}，用{rules['hashtag_count']}，"
                f"发布时机：{rules['best_post_time']}"
            )
        }
