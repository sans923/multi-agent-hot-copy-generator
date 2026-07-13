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

【编排模式】
- fixed（默认）：固定三阶段顺序，见 pipeline_runners.run_full_pipeline
- agentic：任务分级 + Plan&Execute，见 agentic_runners.run_agentic_pipeline
- lead：Lead Agent 总控 + 委派 SubAgent，见 lead_agent.LeadAgent

【实现说明】
阶段逻辑在 app/agents/pipeline_runners.py，与 LangGraph 主流程图共用。
"""

from sqlalchemy.orm import Session

from app.agents.pipeline_runners import PipelineAgents, run_full_pipeline, run_lead_pipeline
from app.agents.agentic_runners import run_agentic_pipeline
from app.config import settings


class AgentOrchestrator:
    """
    Agent 编排器
    
    使用方法：
        orchestrator = AgentOrchestrator()
        result = orchestrator.run(db=db, task_id=123)
    """

    def __init__(self):
        self._agents = PipelineAgents()

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
        mode = (settings.ORCHESTRATION_MODE or "fixed").strip().lower()
        if mode == "lead":
            return run_lead_pipeline(db=db, task_id=task_id, agents=self._agents)
        if mode == "agentic":
            return run_agentic_pipeline(db=db, task_id=task_id, agents=self._agents)
        return run_full_pipeline(db=db, task_id=task_id, agents=self._agents)
