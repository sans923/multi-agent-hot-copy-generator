"""
Agent 编排器
=============
负责按顺序调度 3 个 Agent，传递上下文，处理失败情况

【编排流程】
Task（任务）
    ↓
需求理解 Agent（解析需求 + 找热点）
    ↓ 传递：parsed_requirement + hot_topics
文案创作 Agent（生成初稿）
    ↓ 传递：copy_id + copy_content
审核优化 Agent（评分 + 优化 + 保存终稿）
    ↓
Task.status = COMPLETED

【容错设计】
- 任意 Agent 失败 → Task.status = FAILED，记录 error_message
- 需求理解失败 → 用原始需求直接创作（降级方案）
- 文案创作失败 → 任务失败，返回错误
- 审核失败 → 把初稿标记为终稿（不影响主流程）
"""

import traceback
from sqlalchemy.orm import Session

from app.agents.requirement_agent import RequirementAgent
from app.agents.copywriter_agent import CopywriterAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.models.task import Task, TaskStatus
from app.models.copy import Copy
from app.utils.logger import logger


class AgentOrchestrator:
    """
    Agent 编排器
    
    使用方法：
        orchestrator = AgentOrchestrator()
        result = orchestrator.run(db=db, task_id=123)
    """

    def __init__(self):
        self.requirement_agent = RequirementAgent()
        self.copywriter_agent = CopywriterAgent()
        self.reviewer_agent = ReviewerAgent()

    def run(self, db: Session, task_id: int) -> dict:
        """
        执行完整的多智能体文案生成流程
        
        返回：
            {
                "success": bool,
                "task_id": int,
                "final_copy_id": int,
                "review_score": float,
                "total_tokens": int,
                "stages": {            # 每个阶段的详情
                    "requirement": {...},
                    "copywriter": {...},
                    "reviewer": {...},
                }
            }
        """
        logger.info(f"{'='*50}")
        logger.info(f"开始执行 Agent 编排流程: task_id={task_id}")
        logger.info(f"{'='*50}")

        # 加载任务
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"success": False, "error": f"任务 {task_id} 不存在"}

        total_tokens = 0
        stages = {}

        # ====================================================
        # Stage 1: 需求理解 Agent
        # ====================================================
        logger.info(f"[Stage 1/3] 需求理解 Agent 开始...")

        try:
            req_result = self.requirement_agent.run(
                db=db,
                task_id=task_id,
                raw_requirement=task.raw_requirement,
                platform=task.platform.value if task.platform else "weibo",
            )
            stages["requirement"] = {
                "success": req_result.get("success"),
                "tokens_used": req_result.get("tokens_used", 0),
            }
            total_tokens += req_result.get("tokens_used", 0)

            if not req_result.get("success"):
                logger.warning(f"需求理解Agent失败，使用降级方案: {req_result.get('error')}")
                # 降级：使用原始需求和空热点继续创作
                parsed_requirement = {
                    "raw_requirement": task.raw_requirement,
                    "platform": task.platform.value if task.platform else "weibo",
                    "topic": task.raw_requirement[:20],
                    "style": "口语化",
                    "keywords": [],
                    "word_count": 140,
                }
                hot_topics = []
                context_messages = []
            else:
                parsed_requirement = req_result.get("parsed_requirement", {})
                hot_topics = req_result.get("hot_topics", [])
                context_messages = req_result.get("messages", [])

            logger.info(
                f"[Stage 1/3] 需求理解完成: "
                f"topic={parsed_requirement.get('topic')}, "
                f"hot_topics={len(hot_topics)}"
            )

        except Exception as e:
            logger.exception(f"需求理解Agent异常，使用降级方案")
            parsed_requirement = {
                "raw_requirement": task.raw_requirement,
                "platform": task.platform.value if task.platform else "weibo",
                "topic": task.raw_requirement[:20],
                "style": "口语化",
                "keywords": [],
                "word_count": 140,
            }
            hot_topics = []
            context_messages = []
            stages["requirement"] = {"success": False, "error": str(e)}

        # ====================================================
        # Stage 2: 文案创作 Agent
        # ====================================================
        logger.info(f"[Stage 2/3] 文案创作 Agent 开始...")

        try:
            copy_result = self.copywriter_agent.run(
                db=db,
                task_id=task_id,
                parsed_requirement=parsed_requirement,
                hot_topics=hot_topics,
                context_messages=context_messages,
            )
            stages["copywriter"] = {
                "success": copy_result.get("success"),
                "copy_id": copy_result.get("copy_id"),
                "tokens_used": copy_result.get("tokens_used", 0),
            }
            total_tokens += copy_result.get("tokens_used", 0)

            if not copy_result.get("success"):
                # 文案创作失败，任务整体失败
                error_msg = copy_result.get("error", "文案创作失败")
                self._mark_task_failed(db, task, error_msg)
                return {
                    "success": False,
                    "task_id": task_id,
                    "error": error_msg,
                    "stages": stages,
                    "total_tokens": total_tokens,
                }

            copy_id = copy_result.get("copy_id")
            copy_content = copy_result.get("copy_content", "")

            logger.info(f"[Stage 2/3] 文案创作完成: copy_id={copy_id}")

        except Exception as e:
            error_msg = f"文案创作Agent异常: {str(e)}"
            logger.exception(error_msg)
            self._mark_task_failed(db, task, error_msg)
            return {
                "success": False,
                "task_id": task_id,
                "error": error_msg,
                "stages": stages,
                "total_tokens": total_tokens,
            }

        # ====================================================
        # Stage 3: 审核优化 Agent
        # ====================================================
        logger.info(f"[Stage 3/3] 审核优化 Agent 开始...")

        try:
            review_result = self.reviewer_agent.run(
                db=db,
                task_id=task_id,
                copy_id=copy_id,
                copy_content=copy_content,
                parsed_requirement=parsed_requirement,
                hot_topics=hot_topics,
            )
            stages["reviewer"] = {
                "success": review_result.get("success"),
                "review_score": review_result.get("review_score"),
                "need_optimization": review_result.get("need_optimization"),
                "tokens_used": review_result.get("tokens_used", 0),
            }
            total_tokens += review_result.get("tokens_used", 0)

            if not review_result.get("success"):
                # 审核失败时，把初稿直接作为终稿（降级处理，不让整个任务失败）
                logger.warning(f"审核Agent失败，使用初稿作为终稿: {review_result.get('error')}")
                final_copy_id = self._promote_draft_to_final(db, task_id, copy_id)
                review_score = 0
            else:
                final_copy_id = review_result.get("final_copy_id", copy_id)
                review_score = review_result.get("review_score", 0)

            logger.info(
                f"[Stage 3/3] 审核优化完成: "
                f"score={review_score}, "
                f"final_copy_id={final_copy_id}"
            )

        except Exception as e:
            logger.exception(f"审核Agent异常，使用初稿作为终稿")
            final_copy_id = self._promote_draft_to_final(db, task_id, copy_id)
            review_score = 0
            stages["reviewer"] = {"success": False, "error": str(e)}

        # ====================================================
        # 完成
        # ====================================================
        logger.info(
            f"{'='*50}\n"
            f"Agent 编排流程完成: task_id={task_id}\n"
            f"  最终文案: copy_id={final_copy_id}\n"
            f"  审核得分: {review_score}\n"
            f"  总消耗token: {total_tokens}\n"
            f"{'='*50}"
        )

        return {
            "success": True,
            "task_id": task_id,
            "final_copy_id": final_copy_id,
            "review_score": review_score,
            "total_tokens": total_tokens,
            "stages": stages,
        }

    def _mark_task_failed(self, db: Session, task: Task, error_message: str) -> None:
        """将任务标记为失败"""
        task.status = TaskStatus.FAILED
        task.error_message = error_message[:500]  # 截断防止超长
        db.commit()
        logger.error(f"任务失败: task_id={task.id}, error={error_message}")

    def _promote_draft_to_final(self, db: Session, task_id: int, copy_id: int | None) -> int | None:
        """审核失败时，把初稿升级为终稿（降级处理）"""
        if not copy_id:
            return None
        copy = db.query(Copy).filter(Copy.id == copy_id).first()
        if copy:
            copy.is_final = True
            copy.version = 2
            copy.review_comment = "审核Agent异常，自动采用初稿"
            db.commit()
            logger.info(f"初稿已升级为终稿: copy_id={copy_id}")
        return copy_id
