"""
审核优化相关 Skill（2个）
=========================
Skill 9:  review_copy_quality - 评审文案质量并打分（0-100）
Skill 10: optimize_copy       - 根据审核意见优化文案

这 2 个 Skill 主要供【审核优化 Agent】使用：
  review_copy_quality 打分 -> 若分数 < 阈值 -> optimize_copy 优化
  审稿 Agent 最多迭代 1 次，避免死循环

【评分维度设计（共100分）】
- 标题吸引力    20分：能否引发点击/阅读
- 内容相关性    20分：是否切中主题和热点
- 平台适配性    20分：是否符合平台特性
- 情感共鸣度    20分：能否引发读者共鸣
- 行动引导力    20分：是否有效引导互动

【为什么分数 < 70 才优化？】
行业经验：70分以上的文案通过率已经很高了，
过度优化反而可能破坏文案的自然感，
"够好"比"完美"更重要
"""

from sqlalchemy.orm import Session
from app.skills.base import BaseSkill
from app.utils.logger import logger


# 各平台的审核标准（不同平台的关注点不同）
REVIEW_CRITERIA = {
    "weibo": {
        "title_weight": 0.15,
        "checklist": [
            "开头是否在前20字内抓住注意力",
            "是否在140字以内",
            "是否有话题标签（格式：#话题#）",
            "结尾是否有互动引导",
            "表情符号使用是否适度（3-5个）",
        ]
    },
    "xiaohongshu": {
        "title_weight": 0.25,  # 小红书标题更重要
        "checklist": [
            "标题是否有吸引力（数字/疑问/Emoji）",
            "是否有Emoji（每段开头）",
            "是否有收藏/关注引导",
            "内容是否有干货（可操作的建议）",
            "是否有话题标签（格式：#话题）",
        ]
    },
    "douyin": {
        "title_weight": 0.2,
        "checklist": [
            "前3秒是否有强钩子",
            "语言是否足够口语化",
            "节奏是否快（每句话都在推进）",
            "是否有点赞/评论引导",
            "是否控制在150字以内",
        ]
    },
    "wechat": {
        "title_weight": 0.2,
        "checklist": [
            "标题是否使用了数字+场景公式",
            "是否有小标题分段",
            "内容是否有数据/案例支撑",
            "结尾是否引导分享/在看",
            "段落是否简洁（每段≤200字）",
        ]
    },
    "zhihu": {
        "title_weight": 0.15,
        "checklist": [
            "是否有权威开头",
            "是否有数据/案例支撑",
            "逻辑是否清晰（总-分-总）",
            "是否避免了绝对化表述",
            "内容是否有独特视角",
        ]
    }
}


class ReviewCopyQualitySkill(BaseSkill):
    """
    Skill 9: 评审文案质量
    
    对文案进行多维度评分，找出优点和不足，
    决定是否需要优化（分数 < 70 则需要）
    """

    @property
    def name(self) -> str:
        return "review_copy_quality"

    @property
    def description(self) -> str:
        return (
            "对文案进行质量评审和评分（0-100分）。"
            "从标题吸引力、内容相关性、平台适配性、情感共鸣度、行动引导力五个维度评分。"
            "返回总分、各维度分数、优点、缺点和改进建议。"
            "总分 < 70 分时，应调用 optimize_copy 进行优化。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "copy_content": {
                    "type": "string",
                    "description": "要评审的文案内容"
                },
                "copy_title": {
                    "type": "string",
                    "description": "文案标题（如果有）"
                },
                "platform": {
                    "type": "string",
                    "description": "发布平台"
                },
                "topic": {
                    "type": "string",
                    "description": "文案主题"
                },
                "hot_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要求融入的热榜话题"
                },
                # 评分由 Agent（大模型）来判断，Skill 负责结构化评分结果
                "scores": {
                    "type": "object",
                    "description": "Agent 对各维度的评分",
                    "properties": {
                        "title_appeal": {"type": "integer", "description": "标题吸引力 0-20"},
                        "content_relevance": {"type": "integer", "description": "内容相关性 0-20"},
                        "platform_fit": {"type": "integer", "description": "平台适配性 0-20"},
                        "emotional_resonance": {"type": "integer", "description": "情感共鸣度 0-20"},
                        "call_to_action": {"type": "integer", "description": "行动引导力 0-20"},
                    }
                },
                "strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "文案的优点列表（2-3条）"
                },
                "weaknesses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "文案的不足列表（2-3条）"
                },
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "具体改进建议（2-3条，要可操作）"
                }
            },
            "required": ["copy_content", "platform", "scores", "strengths", "weaknesses", "suggestions"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        copy_content = kwargs.get("copy_content", "")
        copy_title = kwargs.get("copy_title", "")
        platform = kwargs.get("platform", "weibo")
        topic = kwargs.get("topic", "")
        hot_topics = kwargs.get("hot_topics", [])
        scores_raw = kwargs.get("scores", {})
        strengths = kwargs.get("strengths", [])
        weaknesses = kwargs.get("weaknesses", [])
        suggestions = kwargs.get("suggestions", [])

        # 计算总分（5个维度，每个满分20，总分100）
        title_appeal = max(0, min(20, scores_raw.get("title_appeal", 15)))
        content_relevance = max(0, min(20, scores_raw.get("content_relevance", 15)))
        platform_fit = max(0, min(20, scores_raw.get("platform_fit", 15)))
        emotional_resonance = max(0, min(20, scores_raw.get("emotional_resonance", 15)))
        call_to_action = max(0, min(20, scores_raw.get("call_to_action", 15)))

        total_score = (
            title_appeal + content_relevance +
            platform_fit + emotional_resonance + call_to_action
        )

        # 获取平台专属检查清单
        criteria = REVIEW_CRITERIA.get(platform, REVIEW_CRITERIA["weibo"])
        checklist = criteria["checklist"]

        # 简单的规则检查（补充 Agent 评分）
        rule_check_results = self._rule_check(copy_content, copy_title, platform, hot_topics)

        # 综合调整分数（规则检查失败的适当扣分）
        penalty = sum(1 for r in rule_check_results if not r["passed"]) * 2
        total_score = max(0, total_score - penalty)

        need_optimization = total_score < 70
        grade = self._score_to_grade(total_score)

        logger.info(
            f"文案评审完成: platform={platform}, score={total_score}, "
            f"need_optimize={need_optimization}"
        )

        return {
            "success": True,
            "total_score": total_score,
            "grade": grade,
            "scores": {
                "title_appeal": title_appeal,
                "content_relevance": content_relevance,
                "platform_fit": platform_fit,
                "emotional_resonance": emotional_resonance,
                "call_to_action": call_to_action,
            },
            "strengths": strengths,
            "weaknesses": weaknesses,
            "suggestions": suggestions,
            "rule_check": rule_check_results,
            "need_optimization": need_optimization,
            "verdict": (
                f"文案总分 {total_score}/100（{grade}），"
                + ("建议进行优化。" if need_optimization else "质量合格，可以发布。")
            )
        }

    def _rule_check(self, content: str, title: str, platform: str, hot_topics: list) -> list[dict]:
        """基于规则的快速检查"""
        results = []

        # 检查字数
        word_limits = {"weibo": 140, "douyin": 150, "xiaohongshu": 1000, "wechat": 5000, "zhihu": 10000}
        limit = word_limits.get(platform, 500)
        results.append({
            "check": "字数限制",
            "passed": len(content) <= limit,
            "detail": f"当前{len(content)}字，限制{limit}字"
        })

        # 检查是否有话题标签
        if platform in ["weibo", "xiaohongshu", "douyin"]:
            has_hashtag = "#" in content
            results.append({
                "check": "话题标签",
                "passed": has_hashtag,
                "detail": "已有话题标签" if has_hashtag else "缺少话题标签"
            })

        # 检查热榜话题是否融入
        if hot_topics:
            hot_topic_in_content = any(
                ht[:5] in content for ht in hot_topics if len(ht) >= 5
            )
            results.append({
                "check": "热榜话题融入",
                "passed": hot_topic_in_content,
                "detail": "已融入热榜话题" if hot_topic_in_content else "建议融入热榜话题提升曝光"
            })

        return results

    @staticmethod
    def _score_to_grade(score: int) -> str:
        if score >= 90:
            return "S级（爆款潜力）"
        elif score >= 80:
            return "A级（优质内容）"
        elif score >= 70:
            return "B级（合格发布）"
        elif score >= 60:
            return "C级（需要优化）"
        else:
            return "D级（需要重写）"


class OptimizeCopySkill(BaseSkill):
    """
    Skill 10: 优化文案
    
    根据审核意见，对文案进行针对性优化。
    这是审核优化 Agent 调用的最后一个 Skill，
    调用后由 Agent 生成优化后的文案内容，
    再调用 save_final_copy 保存为 version=2 的终稿
    
    【最多迭代1次的机制】
    由 Agent 编排层控制（Phase 4 实现），
    审稿 Agent 检查 iteration 字段，如果已经是第2轮就不再优化
    """

    @property
    def name(self) -> str:
        return "optimize_copy"

    @property
    def description(self) -> str:
        return (
            "根据审核意见优化文案。"
            "当 review_copy_quality 评分低于70分时调用。"
            "传入原文案、审核意见、改进建议，返回优化指令，"
            "Agent 根据这些指令生成优化后的文案版本。"
            "注意：最多优化一次，优化后直接保存为最终版本。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "original_content": {
                    "type": "string",
                    "description": "原始文案内容"
                },
                "review_score": {
                    "type": "integer",
                    "description": "审核得分"
                },
                "weaknesses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "审核发现的不足"
                },
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "具体改进建议"
                },
                "platform": {
                    "type": "string",
                    "description": "目标平台"
                },
                "keep_elements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要保留的优点元素"
                }
            },
            "required": ["original_content", "weaknesses", "suggestions", "platform"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        original_content = kwargs.get("original_content", "")
        review_score = kwargs.get("review_score", 60)
        weaknesses = kwargs.get("weaknesses", [])
        suggestions = kwargs.get("suggestions", [])
        platform = kwargs.get("platform", "weibo")
        keep_elements = kwargs.get("keep_elements", [])

        if not original_content:
            return {"success": False, "error": "原始文案不能为空"}

        # 构建优化指令（由 Agent 执行实际优化）
        optimization_brief = {
            "original_content": original_content,
            "current_score": review_score,
            "target_score": 80,
            "problems_to_fix": weaknesses,
            "specific_actions": suggestions,
            "elements_to_keep": keep_elements,
            "platform": platform,
            "optimization_instruction": (
                f"请根据以下审核意见优化这篇{platform}文案：\n"
                f"当前得分：{review_score}/100\n"
                f"存在问题：{'；'.join(weaknesses)}\n"
                f"改进方向：{'；'.join(suggestions)}\n"
                f"需保留的优点：{'；'.join(keep_elements) if keep_elements else '保持整体风格'}\n\n"
                f"原文案：\n{original_content}\n\n"
                f"请输出优化后的完整文案，不要解释，直接给文案正文。"
            )
        }

        logger.info(
            f"文案优化准备完成: platform={platform}, "
            f"original_score={review_score}, problems={len(weaknesses)}"
        )

        return {
            "success": True,
            "optimization_brief": optimization_brief,
            "instruction": optimization_brief["optimization_instruction"],
            "message": f"优化指令已生成，请根据指令输出优化后的文案（目标分数：80+）"
        }
