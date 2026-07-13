"""
Agent 基类 - Function Calling 循环引擎
========================================
这是 3 个 Agent 共享的核心执行引擎。

【Agent 工作循环（ReAct 模式）】
ReAct = Reasoning + Acting，大模型边推理边行动：

第1轮：
  发送: system_prompt + user_message + tools列表
  收到: tool_call（模型决定调用哪个Skill）
  执行: SkillExecutor.execute(tool_call)
  发送: tool结果 回给模型

第2轮：
  收到: 可能是另一个tool_call，或者最终回答
  如果是tool_call -> 继续循环
  如果是普通消息 -> 循环结束，返回最终回答

【最大迭代次数控制】
每个 Agent 设置 max_tool_calls 上限（默认8次），
避免模型陷入死循环。
审核 Agent 额外限制：最多迭代 1 次优化。

【消息历史管理】
每次 Function Call 都要把结果追加到 messages 列表：
  messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "用户需求"},
    {"role": "assistant", "content": None, "tool_calls": [...]},  # 模型决定调用工具
    {"role": "tool", "content": "工具执行结果"},  # 工具结果
    {"role": "assistant", "content": "最终回答"},  # 最终输出
  ]
"""

import json
import time
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from app.utils.model_roles import get_model_for_role
from app.config import settings
from app.skills import SkillRegistry, SkillExecutor, get_skill_registry
from app.services.audit_service import write_audit_log
from app.utils.llm_client import get_deepseek_client, format_llm_error
from app.utils.logger import logger


class BaseAgent(ABC):
    """
    所有 Agent 的父类，封装 Function Calling 循环逻辑
    
    子类需要实现：
    - name: Agent名称
    - system_prompt: 给大模型的角色定义
    - skill_names: 这个Agent有权使用的Skill列表
    - run(): 业务入口（接收任务参数，组织message，调用 _run_loop）
    """

    def __init__(self):
        self.registry: SkillRegistry = get_skill_registry()
        self.executor: SkillExecutor = SkillExecutor(self.registry)

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称，用于日志和 agent_logs 表记录"""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """
        系统提示词（角色设定）
        告诉模型：你是谁？你的职责是什么？你有哪些工具？如何使用？
        这是影响 Agent 行为最重要的配置
        """
        pass

    @property
    @abstractmethod
    def skill_names(self) -> list[str]:
        """这个 Agent 可以使用的 Skill 名称列表"""
        pass

    @property
    def max_tool_calls(self) -> int:
        """最大工具调用次数（防止死循环），子类可以覆盖"""
        return 8

    @property
    def model_role(self) -> str:
        """子类可覆盖为 planner / pattern / judge；默认 executor。"""
        return "executor"

    @property
    def model(self) -> str:
        """使用的模型，按 model_role 从配置路由。"""
        return get_model_for_role(self.model_role)

    @classmethod
    def _get_client(cls):
        """获取 DeepSeek API 客户端（见 app.utils.llm_client）"""
        return get_deepseek_client()

    @abstractmethod
    def run(self, db: Session, task_id: int, **kwargs) -> dict:
        """
        Agent 业务入口
        子类在这里：
        1. 根据参数构建 user_message
        2. 调用 _run_loop 执行 Function Calling 循环
        3. 解析 _run_loop 的返回，提取需要的字段
        4. 返回结构化结果给编排层
        """
        pass

    def _run_loop(
        self,
        db: Session,
        task_id: int,
        user_message: str,
        extra_messages: list[dict] | None = None,
        iteration: int = 1,
    ) -> dict:
        """
        Function Calling 核心循环
        
        参数：
            db: 数据库会话
            task_id: 任务ID（用于写日志）
            user_message: 用户消息（任务描述）
            extra_messages: 额外的上下文消息（如前一个Agent的输出）
            iteration: 当前迭代轮次（审核Agent用于防止过多迭代）
        
        返回：
            {
                "success": bool,
                "final_response": str,       # 模型的最终文字回答
                "tool_calls_count": int,     # 调用了几次工具
                "tokens_used": int,          # 消耗的 token 数
                "tool_results": list[dict],  # 所有工具调用的结果
            }
        """
        # 获取这个 Agent 可用的工具列表
        tools = self.registry.get_tools_by_names(self.skill_names)
        if not tools:
            logger.warning(f"Agent {self.name}: 没有可用的工具")

        # 构建初始消息列表
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]

        # 加入额外上下文（如上一个 Agent 的输出）
        if extra_messages:
            messages.extend(extra_messages)

        # 加入用户消息
        messages.append({"role": "user", "content": user_message})

        tool_calls_count = 0
        total_tokens = 0
        llm_round = 0
        tool_results = []
        length_continue_used = 0  # 因输出截断而「请继续」的次数
        start_time = time.time()

        logger.info(
            f"Agent [{self.name}] 开始执行: task_id={task_id}, "
            f"iteration={iteration}, tools={self.skill_names}"
        )

        # ====================================================
        # Function Calling 主循环
        # ====================================================
        while tool_calls_count < self.max_tool_calls:

            # 调用大模型
            try:
                response = self._get_client().chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto",  # auto: 让模型自己决定是否调用工具
                    temperature=0.7,     # 0=确定性，1=创造性，0.7适合文案创作
                    max_tokens=settings.DEEPSEEK_MAX_TOKENS,
                )
            except Exception as e:
                err_msg = format_llm_error(e)
                write_audit_log(
                    db,
                    task_id,
                    "llm",
                    f"{self.name}_api_error",
                    agent_name=self.name,
                    status="failed",
                    error_message=err_msg,
                )
                logger.error(
                    f"Agent [{self.name}] API 调用失败: "
                    f"{type(e).__name__}: {repr(e)}"
                )
                return {
                    "success": False,
                    "error": f"大模型 API 调用失败: {err_msg}",
                    "final_response": "",
                    "tool_calls_count": tool_calls_count,
                    "tokens_used": total_tokens,
                    "tool_results": tool_results,
                }

            # 统计 token 消耗
            round_tokens = 0
            if response.usage:
                round_tokens = response.usage.total_tokens
                total_tokens += round_tokens

            choice = response.choices[0]
            message = choice.message
            llm_round += 1

            write_audit_log(
                db,
                task_id,
                "llm",
                f"{self.name}_round_{llm_round}",
                agent_name=self.name,
                input_summary={
                    "model": self.model,
                    "finish_reason": choice.finish_reason,
                    "tool_calls_count": len(message.tool_calls or []),
                },
                output_summary={
                    "content_preview": (message.content or "")[:300] or None,
                    "tool_names": [
                        tc.function.name for tc in (message.tool_calls or [])
                    ],
                    "tokens": round_tokens,
                },
                status="success",
                duration_ms=None,
            )

            # 把模型的回复加入消息历史（重要！模型需要看到自己之前说了什么）
            messages.append(message.model_dump(exclude_unset=False))

            # ---- 判断模型的输出类型 ----

            # 情况1：模型决定调用工具（Function Call）
            if choice.finish_reason == "tool_calls" and message.tool_calls:
                for tool_call in message.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args = tool_call.function.arguments
                    tool_call_id = tool_call.id

                    logger.info(
                        f"Agent [{self.name}] 调用工具: {fn_name}, "
                        f"args: {fn_args[:100]}..."
                    )

                    # 执行 Skill
                    result_json = self.executor.execute(
                        function_name=fn_name,
                        function_args_json=fn_args,
                        db=db,
                        task_id=task_id,
                        agent_name=self.name,
                    )

                    tool_calls_count += 1
                    result_dict = json.loads(result_json)
                    tool_results.append({
                        "skill_name": fn_name,
                        "result": result_dict,
                    })

                    # 把工具执行结果加入消息历史（role=tool）
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,  # 必须和 tool_call.id 对应
                        "content": result_json,
                    })

                # 继续循环，让模型处理工具结果
                continue

            # 情况2：模型给出最终回答（finish_reason == "stop"）
            elif choice.finish_reason == "stop":
                final_response = message.content or ""
                duration = round(time.time() - start_time, 2)

                logger.info(
                    f"Agent [{self.name}] 执行完成: task_id={task_id}, "
                    f"tool_calls={tool_calls_count}, tokens={total_tokens}, "
                    f"duration={duration}s"
                )

                return {
                    "success": True,
                    "final_response": final_response,
                    "tool_calls_count": tool_calls_count,
                    "tokens_used": total_tokens,
                    "tool_results": tool_results,
                    "messages": messages,  # 完整消息历史（传递给下一个Agent用）
                }

            # 情况3：输出被 max_tokens 截断（finish_reason == "length"）
            elif choice.finish_reason == "length":
                partial = (message.content or "").strip()
                if partial and not message.tool_calls:
                    logger.warning(
                        f"Agent [{self.name}] 输出因长度截断，使用已生成内容继续流程"
                    )
                    return {
                        "success": True,
                        "final_response": partial,
                        "tool_calls_count": tool_calls_count,
                        "tokens_used": total_tokens,
                        "tool_results": tool_results,
                        "messages": messages,
                        "truncated": True,
                    }
                if length_continue_used < 1:
                    length_continue_used += 1
                    logger.warning(
                        f"Agent [{self.name}] 输出截断，请求模型继续 "
                        f"(max_tokens={settings.DEEPSEEK_MAX_TOKENS})"
                    )
                    messages.append({
                        "role": "user",
                        "content": "你的上一次回复因长度限制被截断，请从断点继续完成未说完的内容或工具调用。",
                    })
                    continue
                logger.warning(
                    f"Agent [{self.name}] 多次截断仍无法完成: finish_reason=length"
                )
                return {
                    "success": False,
                    "error": (
                        f"模型输出过长被截断，请在 .env 增大 DEEPSEEK_MAX_TOKENS"
                        f"（当前 {settings.DEEPSEEK_MAX_TOKENS}）"
                    ),
                    "final_response": partial,
                    "tool_calls_count": tool_calls_count,
                    "tokens_used": total_tokens,
                    "tool_results": tool_results,
                }

            # 其他未知终止原因
            else:
                logger.warning(
                    f"Agent [{self.name}] 非正常终止: finish_reason={choice.finish_reason}"
                )
                return {
                    "success": False,
                    "error": f"模型非正常终止: {choice.finish_reason}",
                    "final_response": message.content or "",
                    "tool_calls_count": tool_calls_count,
                    "tokens_used": total_tokens,
                    "tool_results": tool_results,
                }

        # 达到最大工具调用次数，强制结束
        logger.warning(
            f"Agent [{self.name}] 达到最大工具调用次数({self.max_tool_calls})，强制终止"
        )
        return {
            "success": False,
            "error": f"达到最大工具调用次数 {self.max_tool_calls}，任务可能未完成",
            "final_response": "",
            "tool_calls_count": tool_calls_count,
            "tokens_used": total_tokens,
            "tool_results": tool_results,
        }
