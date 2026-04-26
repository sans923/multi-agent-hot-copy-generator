"""
需求理解 Agent（Agent 1）
==========================
职责：
  接收用户的原始需求文本，理解用户真正想要什么，
  并找到当前最相关的热榜话题，输出结构化的"创作简报"
  传递给文案创作 Agent

可用 Skill：
  - parse_requirement：把自由文本转为结构化需求
  - search_hotlist：搜索相关热点话题

输出：
  ParsedRequirement 对象（包含主题/平台/风格/热点话题）
  这个输出会作为文案创作 Agent 的输入
"""

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models.task import Task, TaskStatus
from app.skills import REQUIREMENT_AGENT_SKILLS
from app.utils.logger import logger


class RequirementAgent(BaseAgent):
    """
    需求理解 Agent
    
    工作流程：
    1. 接收 task.raw_requirement（用户原始需求）
    2. 调用 parse_requirement Skill 提取结构化信息
    3. 调用 search_hotlist Skill 找相关热点
    4. 把结构化需求+热点信息存回 task.parsed_requirement
    5. 返回给编排层，由编排层传给文案创作 Agent
    """

    @property
    def name(self) -> str:
        return "requirement_agent"

    @property
    def skill_names(self) -> list[str]:
        return REQUIREMENT_AGENT_SKILLS

    @property
    def system_prompt(self) -> str:
        return """你是一个专业的内容营销需求分析师。

你的职责是：
1. 深入理解用户的文案创作需求
2. 提取关键信息：主题、目标平台、写作风格、目标受众、核心关键词
3. 搜索当前最相关的热榜话题，为文案提供热点素材

工作规范：
- 首先调用 parse_requirement 解析用户需求
- 然后调用 search_hotlist 搜索相关热点（用提取的关键词搜索）
- 最终输出一份完整的"创作简报"，包含：
  * 结构化需求（主题/平台/风格/字数要求）
  * 推荐热榜话题（2-3个最相关的）
  * 创作建议（结合热点的写作角度）

注意：
- 如果用户没有明确指定平台，根据内容类型推断最合适的平台
- 如果没有找到相关热点，直接基于主题创作，不强求蹭热点
- 输出简洁清晰，方便文案创作Agent直接使用"""

    def run(self, db: Session, task_id: int, **kwargs) -> dict:
        """
        执行需求理解
        
        参数：
            task_id: 任务ID
            raw_requirement: 用户原始需求（可选，不传则从数据库读）
        
        返回：
            {
                "success": bool,
                "parsed_requirement": dict,  # 结构化需求
                "hot_topics": list,          # 相关热榜话题
                "brief": str,                # 给文案Agent的简报文本
                "tokens_used": int,
            }
        """
        # 1. 从数据库获取任务（也可以通过 kwargs 直接传入）
        raw_requirement = kwargs.get("raw_requirement")
        platform = kwargs.get("platform", "weibo")

        if not raw_requirement:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return {"success": False, "error": f"任务 {task_id} 不存在"}
            raw_requirement = task.raw_requirement
            platform = task.platform.value if task.platform else "weibo"

        # 2. 更新任务状态为处理中
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.PROCESSING
            db.commit()

        # 3. 构建给 Agent 的消息
        user_message = f"""请分析以下文案创作需求：

用户需求：{raw_requirement}
目标平台：{platform}

请执行：
1. 调用 parse_requirement 提取结构化需求
2. 调用 search_hotlist 搜索相关热榜话题（用主题关键词搜索）
3. 综合以上信息，输出创作简报"""

        # 4. 执行 Function Calling 循环
        result = self._run_loop(
            db=db,
            task_id=task_id,
            user_message=user_message,
            iteration=1,
        )

        if not result["success"]:
            logger.error(f"需求理解Agent失败: task_id={task_id}, error={result.get('error')}")
            return result

        # 5. 从工具调用结果中提取关键信息
        parsed_requirement = {}
        hot_topics = []

        for tool_result in result.get("tool_results", []):
            if tool_result["skill_name"] == "parse_requirement":
                parsed_requirement = tool_result["result"].get("parsed_requirement", {})
            elif tool_result["skill_name"] == "search_hotlist":
                hot_topics = tool_result["result"].get("hotlist", [])

        # 6. 把结构化需求存回 task 表
        if task and parsed_requirement:
            task.parsed_requirement = {
                **parsed_requirement,
                "hot_topics": hot_topics[:3],  # 存最多3个热点
            }
            db.commit()
            logger.info(
                f"需求理解完成: task_id={task_id}, "
                f"topic={parsed_requirement.get('topic')}, "
                f"hot_topics_count={len(hot_topics)}"
            )

        return {
            "success": True,
            "parsed_requirement": parsed_requirement,
            "hot_topics": hot_topics,
            "brief": result["final_response"],
            "tokens_used": result["tokens_used"],
            "messages": result.get("messages", []),  # 传给下一个Agent
        }
