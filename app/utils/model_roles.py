"""
模型角色路由
============
按 Agent / 服务角色选择不同 LLM，默认均为 deepseek-chat，可通过 .env 单独升级。
"""

from app.config import settings


def get_model_for_role(role: str) -> str:
    """
    按角色返回模型名。

    角色：
        planner  — 任务规划（复杂任务）
        executor — SubAgent ReAct 执行（默认）
        pattern  — 写作规律提取
        judge    — 目标对齐验证（规则不确定时）
    """
    role = (role or "executor").strip().lower()
    mapping = {
        "planner": settings.PLANNER_MODEL,
        "executor": settings.EXECUTOR_MODEL,
        "pattern": settings.PATTERN_MODEL,
        "judge": settings.JUDGE_MODEL,
    }
    return mapping.get(role) or settings.DEEPSEEK_CHAT_MODEL
