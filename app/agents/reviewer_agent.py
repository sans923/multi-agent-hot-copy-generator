"""
审核优化 Agent（Agent 3）
==========================
职责：合规检测 → 洗稿检测 → 质量评审 → 优化 → 保存终稿
"""

import json

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models.copy import Copy
from app.models.task import Task, TaskStatus
from app.skills import REVIEWER_AGENT_SKILLS
from app.utils.logger import logger
from app.services.task_lifecycle_service import set_task_execution_status


class ReviewerAgent(BaseAgent):
    """审核优化 Agent"""

    @property
    def name(self) -> str:
        return "reviewer_agent"

    @property
    def skill_names(self) -> list[str]:
        return REVIEWER_AGENT_SKILLS

    @property
    def max_tool_calls(self) -> int:
        return 8

    @property
    def system_prompt(self) -> str:
        return """你是一位严格而专业的内容质量审核官，负责把控文案的最终质量。

你的审核标准：
- 合规性：无敏感词/违禁表达
- 原创性：与参考长文无高度重叠（洗稿风险）
- 标题吸引力（20分）、内容相关性（20分）、平台适配性（20分）
- 情感共鸣度（20分）、行动引导力（20分）

工作流程（必须按顺序）：
1. 调用 check_sensitive_words 检测敏感词；未通过则 optimize_copy 修改违禁表达
2. 调用 check_plagiarism_overlap 检测洗稿风险；need_rewrite=true 时必须重写而非微调
3. 调用 review_copy_quality 进行五维度评分（每项0-20分）
4. 若总分 < 70 或 failed_sections 非空，调用 optimize_copy 定向优化一次，输出优化后完整文案
5. 调用 save_final_copy 保存终稿（version=2, is_final=True）
6. 输出简洁审核报告（含合规与重叠检测结果）

重要规则：
- 只优化 1 次；合规/洗稿未通过时优先处理，再谈质量分
- 评分客观；保存时必须 is_final=True"""

    def run(self, db: Session, task_id: int, **kwargs) -> dict:
        copy_id = kwargs.get("copy_id")
        copy_content = kwargs.get("copy_content", "")
        parsed_requirement = kwargs.get("parsed_requirement", {})
        hot_topics = kwargs.get("hot_topics", [])

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

        platform = parsed_requirement.get("platform", "weibo")
        topic = parsed_requirement.get("topic", "")
        hot_titles = [ht.get("title", "") for ht in hot_topics if ht.get("title")]
        article_outline = parsed_requirement.get("article_outline") or {}

        user_message = f"""请对以下{platform}文案进行专业审核：

【待审核文案】
标题：{copy_title or '（无标题）'}
内容：
{copy_content}

【审核背景】
- 主题：{topic}
- 目标平台：{platform}
- 热榜话题：{', '.join(hot_titles[:3]) if hot_titles else '无'}
- 任务ID：{task_id}
- 文案ID：{copy_id}

请严格按工作流程：
1) check_sensitive_words(text=正文, platform="{platform}")
2) check_plagiarism_overlap(text=正文, topic="{topic}")
3) review_copy_quality → 必要时 optimize_copy → save_final_copy
4) 输出审核报告"""

        if platform == "toutiao" and article_outline:
            user_message += f"""

【长文章节契约】
{json.dumps(article_outline, ensure_ascii=False)}

长文审核附加要求：
- review_copy_quality 必须返回 failed_sections，仅列出低于70分的章节
- section_id 必须来自上述提纲，指出具体原因和可执行 rewrite_instruction
- 若需要 optimize_copy，只改进 failed_sections 指定部分，保留其他达标章节的观点和结构
- 最多调用 optimize_copy 一次，禁止循环重写
"""

        result = self._run_loop(
            db=db,
            task_id=task_id,
            user_message=user_message,
            iteration=1,
        )

        if not result["success"]:
            logger.error(f"审核优化Agent失败: task_id={task_id}, error={result.get('error')}")
            return result

        review_score = 0
        need_optimization = False
        final_copy_id = copy_id
        compliance_passed = True
        plagiarism_passed = True
        quality_report = {}
        rewrite_count = 0

        for tool_result in result.get("tool_results", []):
            skill = tool_result["skill_name"]
            res = tool_result["result"]

            if skill == "check_sensitive_words":
                compliance_passed = res.get("passed", True)
            elif skill == "check_plagiarism_overlap":
                plagiarism_passed = res.get("passed", True)
            elif skill == "review_copy_quality":
                review_score = res.get("total_score", 0)
                need_optimization = res.get("need_optimization", False)
                score_labels = {
                    "title_appeal": "标题吸引力",
                    "content_relevance": "内容相关性",
                    "platform_fit": "平台适配性",
                    "emotional_resonance": "情感共鸣度",
                    "call_to_action": "行动引导力",
                }
                quality_report = {
                    "total_score": review_score,
                    "grade": res.get("grade"),
                    "dimensions": [
                        {
                            "name": score_labels.get(name, name),
                            "score": int(score or 0) * 5,
                        }
                        for name, score in (res.get("scores") or {}).items()
                    ],
                    "strengths": res.get("strengths") or [],
                    "weaknesses": res.get("weaknesses") or [],
                    "suggestions": res.get("suggestions") or [],
                    "failed_sections": res.get("failed_sections") or [],
                }
                if copy_id:
                    copy = db.query(Copy).filter(Copy.id == copy_id).first()
                    if copy:
                        copy.review_score = review_score
                        copy.review_comment = res.get("verdict", "")
                        db.commit()
            elif skill == "optimize_copy":
                rewrite_count = 1
            elif skill == "save_final_copy":
                new_id = res.get("copy_id")
                if new_id:
                    final_copy_id = new_id

        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            set_task_execution_status(task, TaskStatus.COMPLETED, reason=None)
            db.commit()

        logger.info(
            f"审核优化完成: task_id={task_id}, score={review_score}, "
            f"compliance={compliance_passed}, plagiarism={plagiarism_passed}, "
            f"final_copy_id={final_copy_id}"
        )

        return {
            "success": True,
            "final_copy_id": final_copy_id,
            "review_score": review_score,
            "need_optimization": need_optimization,
            "compliance_passed": compliance_passed,
            "plagiarism_passed": plagiarism_passed,
            "final_content": result["final_response"],
            "review_report": result["final_response"],
            "quality_report": quality_report,
            "rewrite_count": rewrite_count,
            "tokens_used": result["tokens_used"],
        }
