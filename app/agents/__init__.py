"""
Agents 包
=========
3 个 Agent + 1 个编排器（惰性导入，避免与 skills 包循环依赖）
"""

__all__ = [
    "AgentOrchestrator",
    "RequirementAgent",
    "CopywriterAgent",
    "ReviewerAgent",
]


def __getattr__(name: str):
    if name == "AgentOrchestrator":
        from app.agents.orchestrator import AgentOrchestrator
        return AgentOrchestrator
    if name == "RequirementAgent":
        from app.agents.requirement_agent import RequirementAgent
        return RequirementAgent
    if name == "CopywriterAgent":
        from app.agents.copywriter_agent import CopywriterAgent
        return CopywriterAgent
    if name == "ReviewerAgent":
        from app.agents.reviewer_agent import ReviewerAgent
        return ReviewerAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
