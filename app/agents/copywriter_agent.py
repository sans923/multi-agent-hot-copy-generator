"""
文案创作 Agent（Agent 2）
==========================
职责：
  接收需求理解 Agent 的输出（结构化需求 + 热点话题），
  调用文案创作相关的 Skill，生成完整的文案初稿，
  保存到数据库（version=1）

可用 Skill（5个）：
  - get_platform_rules：获取目标平台的创作规范
  - search_similar_copies：检索相似历史文案作为参考
  - generate_outline：生成文案大纲
  - write_copy_draft：根据大纲生成文案
  - add_hashtags：添加话题标签
  - save_final_copy：保存文案到数据库

创作流水线：
  get_platform_rules -> search_similar_copies ->
  generate_outline -> write_copy_draft ->
  add_hashtags -> save_final_copy
"""

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.skills import COPYWRITER_AGENT_SKILLS
from app.utils.logger import logger


class CopywriterAgent(BaseAgent):
    """
    文案创作 Agent
    
    这是 3 个 Agent 中调用工具最多的一个，
    需要按顺序调用 6 个 Skill 完成创作流水线
    """

    @property
    def name(self) -> str:
        return "copywriter_agent"

    @property
    def skill_names(self) -> list[str]:
        return COPYWRITER_AGENT_SKILLS

    @property
    def max_tool_calls(self) -> int:
        return 10  # 文案创作需要更多工具调用步骤

    @property
    def system_prompt(self) -> str:
        return """你是一位资深的社交媒体爆款文案创作专家，熟悉各平台的内容规律和用户心理。

你的创作原则：
- 结合热点，让文案更有时效性和传播力
- 开头必须在3秒内抓住读者注意力
- 内容要有"人味"，不能像机器写的
- 每个平台都有独特的语言风格，严格遵守平台规范

工作流程（必须按顺序执行）：
1. 调用 get_platform_rules 了解目标平台规范
2. 调用 search_similar_copies 参考历史爆款文案的风格
3. 调用 generate_outline 设计文案结构框架
4. 根据 write_copy_draft 返回的写作摘要，直接创作文案正文
5. 调用 add_hashtags 添加合适的话题标签
6. 调用 save_final_copy 保存初稿（version=1）

创作时注意：
- write_copy_draft 会返回详细的写作摘要和指令，仔细阅读后再创作
- 文案要自然流畅，符合平台用户的阅读习惯
- 融入热榜话题，但要融合自然，不要生硬插入
- 保存时 version=1, is_final=False（初稿，等待审核）"""

    def run(
        self,
        db: Session,
        task_id: int,
        **kwargs
    ) -> dict:
        """
        执行文案创作
        
        参数：
            task_id: 任务ID
            parsed_requirement: 结构化需求（来自需求理解Agent）
            hot_topics: 热榜话题列表
            context_messages: 需求理解Agent的消息历史（可选，提供上下文）
        
        返回：
            {
                "success": bool,
                "copy_id": int,       # 保存的文案ID
                "copy_content": str,  # 文案正文
                "copy_title": str,    # 文案标题
                "hashtags": list,     # 话题标签
                "tokens_used": int,
            }
        """
        parsed_requirement = kwargs.get("parsed_requirement", {})
        hot_topics = kwargs.get("hot_topics", [])
        context_messages = kwargs.get("context_messages", [])

        # 如果没有传入parsed_requirement，从数据库读
        if not parsed_requirement:
            from app.models.task import Task
            task = db.query(Task).filter(Task.id == task_id).first()
            if task and task.parsed_requirement:
                parsed_requirement = task.parsed_requirement
                hot_topics = parsed_requirement.get("hot_topics", [])

        # 提取关键参数
        platform = parsed_requirement.get("platform", "weibo")
        topic = parsed_requirement.get("topic", "热点话题")
        style = parsed_requirement.get("style", "口语化")
        keywords = parsed_requirement.get("keywords", [])
        word_count = parsed_requirement.get("word_count", 140)

        # 热榜话题标题列表（用于传给Skill）
        hot_titles = [ht.get("title", "") for ht in hot_topics if ht.get("title")]

        # 构建创作指令
        user_message = f"""请为以下需求创作一篇{platform}爆款文案：

【创作需求】
- 主题：{topic}
- 平台：{platform}
- 风格：{style}
- 字数要求：约{word_count}字
- 核心关键词：{', '.join(keywords)}
- 相关热榜话题：{', '.join(hot_titles[:3]) if hot_titles else '无特定热点，自主发挥'}
- 任务ID：{task_id}（保存文案时使用）

请按照工作流程逐步执行，最终输出一篇高质量的{platform}文案。"""

        # 执行 Function Calling 循环
        # 如果有上下文消息，传入让模型了解需求背景
        # 只取最近的几条，避免 context 过长
        extra_messages = []
        if context_messages:
            # 从需求理解Agent的消息历史中只取 assistant 的最后回复
            assistant_msgs = [m for m in context_messages if m.get("role") == "assistant" and m.get("content")]
            if assistant_msgs:
                extra_messages = [
                    {
                        "role": "user",
                        "content": f"【需求分析结果参考】\n{assistant_msgs[-1]['content']}"
                    }
                ]

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

        # 从工具调用结果中提取保存的文案信息
        copy_id = None
        copy_content = result["final_response"]
        copy_title = ""
        hashtags = []

        for tool_result in result.get("tool_results", []):
            if tool_result["skill_name"] == "save_final_copy":
                copy_id = tool_result["result"].get("copy_id")
            elif tool_result["skill_name"] == "add_hashtags":
                hashtags = tool_result["result"].get("hashtags", [])

        logger.info(
            f"文案创作完成: task_id={task_id}, copy_id={copy_id}, "
            f"platform={platform}, tokens={result['tokens_used']}"
        )

        return {
            "success": True,
            "copy_id": copy_id,
            "copy_content": copy_content,
            "copy_title": copy_title,
            "hashtags": hashtags,
            "tokens_used": result["tokens_used"],
            "tool_results": result["tool_results"],
            "messages": result.get("messages", []),
        }
