"""
编排引擎抽象层
================
本模块定义「编排引擎」的统一接口 OrchestrationEngine。

【为什么要这一层？】
项目原本只有一种编排实现：自研的 AgentOrchestrator（顺序流水线）。
现在要引入第二种实现：基于 LangGraph 的 DeerFlow 2.0 风格编排。
为了让业务侧（app/api/v1/tasks.py）无需关心"到底用哪种引擎"，
我们在两种实现之上抽出一个统一接口，业务侧只依赖这个接口 + 工厂，
通过配置 settings.ORCHESTRATION_ENGINE 选择具体实现。

【唯一硬契约】
    run(db, task_id) -> dict
与现有 AgentOrchestrator.run(db, task_id) -> dict 完全对齐，
保证 tasks.py 的改动最小（只把"直接 new AgentOrchestrator"换成"按配置取引擎"）。

返回 dict 结构（成功）：
    {
        "success": True,
        "task_id": int,
        "final_copy_id": int | None,
        "review_score": float,
        "total_tokens": int,
        "stages": dict,
    }
返回 dict 结构（失败）：
    {
        "success": False,
        "task_id": int,
        "error": str,
        "stages": dict,
        "total_tokens": int,
    }

【预留扩展点】
start / resume / get_state 面向「人工介入（human-in-the-loop）」场景，
属于可选能力：不支持该能力的引擎（如自研 native）保持默认实现即可，
调用时会明确抛出 NotImplementedError，而不是静默降级。
当前阶段（P0）业务侧只使用 run()，扩展点先占位、后续阶段再落地。
"""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session


class OrchestrationEngine(ABC):
    """
    编排引擎统一接口。

    子类（实现）：
    - NativeOrchestrationEngine：适配现有自研 AgentOrchestrator（第一个实现）
    - LangGraphOrchestrationEngine：基于 LangGraph 的编排（后续阶段）
    """

    #: 引擎名称，与 settings.ORCHESTRATION_ENGINE 的取值对应（如 "native" / "langgraph"）
    name: str = "base"

    @abstractmethod
    def run(self, db: Session, task_id: int) -> dict:
        """
        执行一次完整的多智能体文案生成流程（同步、阻塞直到完成）。

        参数：
            db: 数据库会话（由调用方在后台线程中创建并负责关闭）
            task_id: 任务ID

        返回：
            dict，结构见模块顶部说明（与 AgentOrchestrator.run 对齐）
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 以下为「人工介入」预留扩展点，默认不支持；需要的引擎自行覆盖。
    # ------------------------------------------------------------------

    def start(self, db: Session, task_id: int, *, thread_id: str | None = None) -> dict:
        """启动一个可中断/可恢复的流程（human-in-the-loop）。默认不支持。"""
        raise NotImplementedError(
            f"引擎 '{self.name}' 不支持 start()（人工介入扩展点尚未实现）"
        )

    def resume(self, db: Session, task_id: int, *, thread_id: str, human_input: dict) -> dict:
        """在人工介入后恢复流程。默认不支持。"""
        raise NotImplementedError(
            f"引擎 '{self.name}' 不支持 resume()（人工介入扩展点尚未实现）"
        )

    def get_state(self, *, thread_id: str) -> dict:
        """查询某次流程的中间状态。默认不支持。"""
        raise NotImplementedError(
            f"引擎 '{self.name}' 不支持 get_state()（人工介入扩展点尚未实现）"
        )

    def close(self) -> None:
        """释放引擎持有的可关闭资源；无资源引擎保持空操作。"""

    def __enter__(self) -> "OrchestrationEngine":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
