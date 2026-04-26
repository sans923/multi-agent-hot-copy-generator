"""
审核优化 Agent（Agent 3）
==========================
职责：
  接收文案创作 Agent 生成的初稿，
  进行多维度质量评审（0-100分），
  如果分数 < 70，进行一次优化，
  最终保存终稿（version=2）

可用 Skill（3个）：
  - review_copy_quality：评审文案质量并打分
  - optimize_copy：根据审核意见优化文案
  - save_final_copy：保存终稿

【最多迭代 1 次的设计】
为什么最多迭代 1 次？
- 避免"永远觉得不够好"的死循环
- 实践证明：1次针对性优化足以把文案提升10-15分
- 过度打磨反而让文案失去自然感
- 节省 API 调用成本

迭代逻辑：
  score >= 70: 直接保存初稿为终稿
  score < 70: 优化一次 -> 保存为 version=2 的终稿
  不管score多少：都只优化1次，不再循环
"""

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models.copy import Copy
from app.models.task import Task, TaskStatus
from app.skills import REVIEWER_AGENT_SKILLS
from app.utils.logger import logger


class ReviewerAgent(BaseAgent):
    """
    审核优化 Agent
    
    是整个 Agent 链的最后一环，确保输出质量
    """

    @property
    def name(self) -> str:
        return "reviewer_agent"

    @property
    def skill_names(self) -> list[str]:
        return REVIEWER_AGENT_SKILLS

    @property
    def max_tool_calls(self) -> int:
        return 6  # 审核+优化+保存，最多6次

    @property
    def system_prompt(self) -> str:
        return """你是一位严格而专业的内容质量审核官，负责把控文案的最终质量。

你的审核标准：
- 标题吸引力（20分）：能否引发点击/阅读
- 内容相关性（20分）：是否切中主题和热点  
- 平台适配性（20分）：是否符合平台特性和规范
- 情感共鸣度（20分）：能否引发读者共鸣
- 行动引导力（20分）：是否有效引导互动/转发

工作流程：
1. 调用 review_copy_quality 进行评审打分（必须给出5个维度的分数）
2. 如果总分 < 70，调用 optimize_copy 获取优化指令，然后输出优化后的文案
3. 调用 save_final_copy 保存终稿
   - 如果分数 >= 70：直接保存初稿（version=2, is_final=True）
   - 如果优化过：保存优化后版本（version=2, is_final=True）
4. 输出最终审核报告

重要规则：
- 只优化 1 次，不管优化后得分如何都直接保存
- 评分要客观，不能因为是AI生成就一律给高分
- 优化要针对具体问题，不是重写整篇
- 保存时必须设置 is_final=True"""

    def run(
        self,
        db: Session,
        task_id: int,
        **kwargs
    ) -> dict:
        """
        执行审核优化
        
        参数：
            task_id: 任务ID
            copy_id: 要审核的文案ID（来自文案创作Agent）
            copy_content: 文案内容（可选，不传则从数据库读）
            parsed_requirement: 原始需求（用于评审时对照需求）
            hot_topics: 热榜话题（检查是否融入）
        
        返回：
            {
                "success": bool,
                "final_copy_id": int,    # 最终文案ID
                "review_score": float,   # 审核得分
                "need_optimization": bool,
                "final_content": str,    # 最终文案内容
                "review_report": str,    # 审核报告
                "tokens_used": int,
            }
        """
        copy_id = kwargs.get("copy_id")
        copy_content = kwargs.get("copy_content", "")
        parsed_requirement = kwargs.get("parsed_requirement", {})
        hot_topics = kwargs.get("hot_topics", [])

        # 从数据库读取文案
        if not copy_content and copy_id:
            copy = db.query(Copy).filter(Copy.id == copy_id).first()
            if copy:
                copy_content = copy.content
                copy_title = copy.title or ""
            else:
                return {"success": False, "error": f"文案 {copy_id} 不存在"}
        else:
            copy_title = kwargs.get("copy_title", "")

        if not copy_content:
            # 尝试从任务中读取最新文案
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                latest_copy = (
                    db.query(Copy)
                    .filter(Copy.task_id == task_id)
                    .order_by(Copy.created_at.desc())
                    .first()
                )
                if latest_copy:
                    copy_content = latest_copy.content
                    copy_id = latest_copy.id
                    copy_title = latest_copy.title or ""

        if not copy_content:
            return {"success": False, "error": "找不到要审核的文案内容"}

        # 提取参数
        platform = parsed_requirement.get("platform", "weibo")
        topic = parsed_requirement.get("topic", "")
        hot_titles = [ht.get("title", "") for ht in hot_topics if ht.get("title")]

        # 构建审核指令
        user_message = f"""请对以下{platform}文案进行专业审核：

【待审核文案】
标题：{copy_title or '（无标题）'}
内容：
{copy_content}

【审核背景】
- 主题：{topic}
- 目标平台：{platform}
- 融入的热榜话题：{', '.join(hot_titles[:3]) if hot_titles else '无'}
- 任务ID：{task_id}（保存时使用）
- 原始文案ID：{copy_id}

请执行：
1. 调用 review_copy_quality 对5个维度逐一评分（每项0-20分）
2. 如果总分 < 70，调用 optimize_copy 获取优化方向，然后输出优化后的完整文案
3. 调用 save_final_copy 保存最终版本（version=2, is_final=True）
4. 输出简洁的审核报告"""

        result = self._run_loop(
            db=db,
            task_id=task_id,
            user_message=user_message,
            iteration=1,
        )

        if not result["success"]:
            logger.error(f"审核优化Agent失败: task_id={task_id}, error={result.get('error')}")
            return result

        # 从工具调用结果提取信息
        review_score = 0
        need_optimization = False
        final_copy_id = copy_id  # 默认用初稿ID

        for tool_result in result.get("tool_results", []):
            if tool_result["skill_name"] == "review_copy_quality":
                review_score = tool_result["result"].get("total_score", 0)
                need_optimization = tool_result["result"].get("need_optimization", False)

                # 把审核分数写回数据库
                if copy_id:
                    copy = db.query(Copy).filter(Copy.id == copy_id).first()
                    if copy:
                        copy.review_score = review_score
                        copy.review_comment = tool_result["result"].get("verdict", "")
                        db.commit()

            elif tool_result["skill_name"] == "save_final_copy":
                # 如果有新保存的文案，更新 final_copy_id
                new_id = tool_result["result"].get("copy_id")
                if new_id:
                    final_copy_id = new_id

        # 更新任务状态为完成
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.COMPLETED
            db.commit()

        logger.info(
            f"审核优化完成: task_id={task_id}, "
            f"review_score={review_score}, "
            f"need_optimization={need_optimization}, "
            f"final_copy_id={final_copy_id}"
        )

        return {
            "success": True,
            "final_copy_id": final_copy_id,
            "review_score": review_score,
            "need_optimization": need_optimization,
            "final_content": result["final_response"],
            "review_report": result["final_response"],
            "tokens_used": result["tokens_used"],
        }
