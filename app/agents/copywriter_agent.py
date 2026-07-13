"""
文案创作 Agent（Agent 2）
==========================
检索爆款长文 → 提取抽象写作规律 → 按 pattern 生成文案初稿。
"""

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.skills import COPYWRITER_AGENT_SKILLS
from app.utils.logger import logger


class CopywriterAgent(BaseAgent):
    """文案创作 Agent"""

    @property
    def name(self) -> str:
        return "copywriter_agent"

    @property
    def skill_names(self) -> list[str]:
        return COPYWRITER_AGENT_SKILLS

    @property
    def max_tool_calls(self) -> int:
        return 14

    @property
    def system_prompt(self) -> str:
        return """你是一位资深的社交媒体爆款文案创作专家，熟悉各平台的内容规律和用户心理。

你的创作原则：
- 结合热点，让文案更有时效性和传播力
- 开头必须在3秒内抓住读者注意力
- 学习爆款长文的「结构与节奏」，绝不照搬参考文原句
- 每个平台都有独特的语言风格，严格遵守平台规范

工作流程（必须按顺序执行）：
1. 调用 get_platform_rules 了解目标平台规范
2. 调用 get_style_card 尝试加载已沉淀的写作规律（若无则继续 3-4）
3. 调用 search_hot_articles_by_topic 按话题+点赞量检索最热长文（sort_by=likes）
4. 调用 extract_writing_pattern 从长文提取抽象 writing_pattern（禁止抄原文）
5. 调用 search_similar_copies 参考本系统历史爆款文案
6. 调用 generate_outline，必须传入 writing_pattern
7. 调用 write_copy_draft，传入 outline 与 writing_pattern，再创作正文
8. 调用 add_hashtags 添加话题标签
9. 调用 save_final_copy 保存初稿（version=1, is_final=False）

重要：
- writing_pattern 是抽象规律 JSON，不是范文；正文必须原创
- 若 get_style_card 已返回 writing_pattern，可跳过 3-4，但仍需 search_similar_copies
- generate_outline / write_copy_draft 都必须携带 writing_pattern"""

    def run(self, db: Session, task_id: int, **kwargs) -> dict:
        parsed_requirement = kwargs.get("parsed_requirement", {})
        hot_topics = kwargs.get("hot_topics", [])
        context_messages = kwargs.get("context_messages", [])

        if not parsed_requirement:
            from app.models.task import Task
            task = db.query(Task).filter(Task.id == task_id).first()
            if task and task.parsed_requirement:
                parsed_requirement = task.parsed_requirement
                hot_topics = parsed_requirement.get("hot_topics", [])

        platform = parsed_requirement.get("platform", "weibo")
        topic = parsed_requirement.get("topic", "热点话题")
        style = parsed_requirement.get("style", "口语化")
        keywords = parsed_requirement.get("keywords", [])
        word_count = parsed_requirement.get("word_count", 140)
        hot_titles = [ht.get("title", "") for ht in hot_topics if ht.get("title")]

        user_message = f"""请为以下需求创作一篇{platform}爆款文案：

【创作需求】
- 主题：{topic}
- 平台：{platform}
- 风格：{style}
- 字数要求：约{word_count}字
- 核心关键词：{', '.join(keywords)}
- 相关热榜话题：{', '.join(hot_titles[:3]) if hot_titles else '无特定热点，自主发挥'}
- 任务ID：{task_id}（保存文案时使用）

请严格按工作流程：
1) get_style_card(topic="{topic}") 或 search_hot_articles_by_topic + extract_writing_pattern
2) 用 writing_pattern 调用 generate_outline 与 write_copy_draft
3) 完成标签与保存

禁止照搬任何参考长文原句，只学习抽象结构与节奏。"""

        extra_messages = []
        if context_messages:
            assistant_msgs = [
                m for m in context_messages
                if m.get("role") == "assistant" and m.get("content")
            ]
            if assistant_msgs:
                extra_messages = [{
                    "role": "user",
                    "content": f"【需求分析结果参考】\n{assistant_msgs[-1]['content']}",
                }]

        result = self._run_loop(
            db=db,
            task_id=task_id,
            user_message=user_message,
            extra_messages=extra_messages,
            iteration=1,
        )

        if not result["success"]:
            logger.error(f"文案创作Agent失败: task_id={task_id}, error={result.get('error')}")
            return result

        copy_id = None
        copy_content = result["final_response"]
        copy_title = ""
        hashtags = []
        writing_pattern = None

        for tool_result in result.get("tool_results", []):
            skill = tool_result["skill_name"]
            res = tool_result["result"]
            if skill == "save_final_copy":
                copy_id = res.get("copy_id")
            elif skill == "add_hashtags":
                hashtags = res.get("hashtags", [])
            elif skill in ("extract_writing_pattern", "get_style_card"):
                if res.get("writing_pattern"):
                    writing_pattern = res.get("writing_pattern")

        logger.info(
            f"文案创作完成: task_id={task_id}, copy_id={copy_id}, "
            f"platform={platform}, pattern={bool(writing_pattern)}, "
            f"tokens={result['tokens_used']}"
        )

        return {
            "success": True,
            "copy_id": copy_id,
            "copy_content": copy_content,
            "copy_title": copy_title,
            "hashtags": hashtags,
            "writing_pattern": writing_pattern,
            "tokens_used": result["tokens_used"],
            "tool_results": result["tool_results"],
            "messages": result.get("messages", []),
        }
