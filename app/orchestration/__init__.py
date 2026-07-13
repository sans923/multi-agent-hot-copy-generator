"""
编排引擎包
==========
对外暴露：
- OrchestrationEngine：编排引擎统一接口（抽象基类）
- get_orchestration_engine：按配置/名称获取引擎实例的工厂
- register_engine：注册新引擎（后续阶段接入 LangGraph 引擎时使用）
- NativeOrchestrationEngine：自研编排引擎（第一个实现）

业务侧（app/api/v1/tasks.py）只需：
    from app.orchestration import get_orchestration_engine
    engine = get_orchestration_engine(settings.ORCHESTRATION_ENGINE)
    result = engine.run(db=db, task_id=task_id)
"""

from app.orchestration.base import OrchestrationEngine
from app.orchestration.factory import (
    DEFAULT_ENGINE,
    get_orchestration_engine,
    register_engine,
)
from app.orchestration.langgraph_engine import LangGraphOrchestrationEngine
from app.orchestration.native_engine import NativeOrchestrationEngine

__all__ = [
    "OrchestrationEngine",
    "NativeOrchestrationEngine",
    "LangGraphOrchestrationEngine",
    "get_orchestration_engine",
    "register_engine",
    "DEFAULT_ENGINE",
]
