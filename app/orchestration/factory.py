"""
编排引擎工厂
============
根据配置 settings.ORCHESTRATION_ENGINE 返回对应的编排引擎实例。

【注册表模式】
用一个「名称 -> 引擎构造函数」的注册表管理所有可用引擎：
- P0 阶段只注册 native（自研）；
- 后续阶段接入 LangGraph 引擎时，只需在此 register("langgraph", ...)，
  业务侧（tasks.py）一行都不用改。

【容错策略：未知/未实现引擎回退 native】
本工厂在 FastAPI 后台线程里被调用，必须健壮：
- 配置了一个尚未注册或拼错的引擎名 -> 记日志告警并回退到 native，
  保证任务仍能正常执行（而不是因为配置问题直接崩）。
切回 native 即恢复现状，这与「双引擎可灰度、可回滚」的设计目标一致。
"""

from typing import Callable

from app.config import settings
from app.orchestration.base import OrchestrationEngine
from app.orchestration.langgraph_engine import LangGraphOrchestrationEngine
from app.orchestration.native_engine import NativeOrchestrationEngine
from app.utils.logger import logger


# 引擎注册表：name -> 返回 OrchestrationEngine 实例的工厂函数
# 用工厂函数（而非直接放实例）以便惰性构造，避免模块加载期产生副作用。
_ENGINE_REGISTRY: dict[str, Callable[[], OrchestrationEngine]] = {
    "native": NativeOrchestrationEngine,
    "langgraph": LangGraphOrchestrationEngine,
}

#: 兜底引擎名称（任何异常情况都回退到它）
DEFAULT_ENGINE = "native"


def register_engine(name: str, factory: Callable[[], OrchestrationEngine]) -> None:
    """
    注册一个编排引擎（供后续阶段接入 LangGraph 引擎时调用）。

    参数：
        name: 引擎名称（与 settings.ORCHESTRATION_ENGINE 取值对应）
        factory: 无参可调用对象，调用后返回一个 OrchestrationEngine 实例
    """
    if name in _ENGINE_REGISTRY:
        logger.warning(f"编排引擎 '{name}' 已注册，将被覆盖")
    _ENGINE_REGISTRY[name] = factory
    logger.debug(f"编排引擎已注册: {name}")


def get_orchestration_engine(name: str | None = None) -> OrchestrationEngine:
    """
    按名称获取编排引擎实例。

    参数：
        name: 引擎名称；为 None 时读取 settings.ORCHESTRATION_ENGINE

    返回：
        OrchestrationEngine 实例。未知/未注册的名称会告警并回退到 native。
    """
    engine_name = (name or settings.ORCHESTRATION_ENGINE or DEFAULT_ENGINE).strip()

    factory = _ENGINE_REGISTRY.get(engine_name)
    if factory is None:
        logger.warning(
            f"未知或尚未注册的编排引擎 '{engine_name}'，"
            f"可用引擎: {list(_ENGINE_REGISTRY.keys())}；回退到 '{DEFAULT_ENGINE}'"
        )
        factory = _ENGINE_REGISTRY[DEFAULT_ENGINE]
        engine_name = DEFAULT_ENGINE

    engine = factory()
    logger.info(f"使用编排引擎: {engine_name}")
    return engine
