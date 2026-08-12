"""
Skill 基础设施 - Function Calling 注册与调用机制
================================================
这是整个多智能体系统的"工具箱"核心。

【什么是 Function Calling？】
DeepSeek/OpenAI 的大模型不仅能聊天，还能"调用函数"：
1. 你告诉模型"有哪些工具可以用"（提供 tools 列表）
2. 模型根据用户需求，自主决定"是否调用工具"以及"调用哪个"
3. 模型返回 tool_call 请求（包含函数名+参数）
4. 你的代码执行这个函数，把结果返回给模型
5. 模型拿到结果后，继续推理，生成最终回答

【架构图】
Agent（大脑）
    ↓ 发送 prompt + tools 列表
DeepSeek API
    ↓ 返回 tool_call（决定调用哪个Skill）
SkillExecutor（执行器）
    ↓ 根据函数名找到对应 Skill
Skill（具体实现）
    ↓ 执行（查数据库/调API/搜向量库）
    ↓ 返回结果给模型
Agent 继续推理...

【设计模式：注册器模式（Registry Pattern）】
把所有 Skill 统一注册到一个字典里：
  {"search_hotlist": <SearchHotlistSkill>, "parse_requirement": <ParseRequirementSkill>, ...}
Agent 调用时只需要传函数名，注册器负责找到并执行对应的 Skill
"""

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Collection
from typing import Any, Callable
from sqlalchemy.orm import Session

from app.skills.skill_response import normalize_skill_result, skill_fail
from app.services.audit_service import write_audit_log
from app.utils.logger import logger


# ====================================================
# Skill 基类
# ====================================================

class BaseSkill(ABC):
    """
    所有 Skill 的父类
    
    每个 Skill 对应 Function Calling 中的一个"工具"，需要提供：
    1. name: 工具名称（模型调用时用的标识符，必须唯一）
    2. description: 工具描述（告诉模型这个工具是干什么的，很重要！）
    3. parameters_schema: 参数定义（JSON Schema 格式，模型按此生成参数）
    4. execute(): 实际执行逻辑
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill 名称，对应 Function Calling 中的 function.name"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Skill 描述，这段文字直接传给大模型看
        写清楚：这个工具做什么？什么时候用？输入输出是什么？
        描述越清晰，模型调用越准确！
        """
        pass

    @property
    @abstractmethod
    def parameters_schema(self) -> dict:
        """
        参数定义，JSON Schema 格式
        
        示例：
        {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认5",
                    "default": 5
                }
            },
            "required": ["keyword"]
        }
        """
        pass

    @abstractmethod
    def execute(self, db: Session, **kwargs) -> dict:
        """
        Skill 执行逻辑
        
        参数：
            db: 数据库会话（查数据库用）
            **kwargs: 模型传来的参数（和 parameters_schema 对应）
        
        返回：
            dict: 执行结果，会被序列化成 JSON 返回给模型
                  必须包含 "success" 字段
        """
        pass

    def to_openai_tool(self) -> dict:
        """
        转换为 OpenAI/DeepSeek Function Calling 的 tool 格式
        
        这个格式是固定的，发给模型时必须是这个结构：
        {
            "type": "function",
            "function": {
                "name": "skill名称",
                "description": "描述",
                "parameters": { ...JSON Schema... }
            }
        }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            }
        }


# ====================================================
# Skill 注册器
# ====================================================

class SkillRegistry:
    """
    Skill 注册器 - 管理所有可用的 Skill
    
    使用注册器的好处：
    - 统一管理所有工具，增加新工具只需注册，不需要改 Agent 代码
    - Agent 只依赖注册器接口，不直接依赖具体 Skill（低耦合）
    - 方便按需组合：不同 Agent 可以使用不同的 Skill 子集
    """

    def __init__(self):
        # 核心数据结构：name -> Skill 实例
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> "SkillRegistry":
        """
        注册一个 Skill
        
        支持链式调用：
            registry.register(skill1).register(skill2).register(skill3)
        """
        if skill.name in self._skills:
            logger.warning(f"Skill '{skill.name}' 已存在，将被覆盖")
        self._skills[skill.name] = skill
        logger.debug(f"Skill 已注册: {skill.name}")
        return self

    def get(self, name: str) -> BaseSkill | None:
        """根据名称获取 Skill"""
        return self._skills.get(name)

    def get_all_tools(self) -> list[dict]:
        """
        获取所有 Skill 的 OpenAI tool 格式列表
        发给大模型时用这个，告诉模型"你有哪些工具可以用"
        """
        return [skill.to_openai_tool() for skill in self._skills.values()]

    def get_tools_by_names(self, names: list[str]) -> list[dict]:
        """
        获取指定名称的 Skill 工具列表
        不同 Agent 使用不同的工具子集
        """
        tools = []
        for name in names:
            skill = self._skills.get(name)
            if skill:
                tools.append(skill.to_openai_tool())
            else:
                logger.warning(f"Skill '{name}' 未注册，已跳过")
        return tools

    def list_skills(self) -> list[str]:
        """列出所有已注册的 Skill 名称（调试用）"""
        return list(self._skills.keys())

    def __len__(self) -> int:
        return len(self._skills)


# ====================================================
# Skill 执行器
# ====================================================

class SkillExecutor:
    """
    Skill 执行器 - 接收模型的 tool_call，找到对应 Skill 并执行
    
    工作流程：
    1. 模型返回 tool_call: {"name": "search_hotlist", "arguments": '{"keyword":"AI"}'}
    2. 执行器解析 arguments（JSON字符串 → dict）
    3. 在注册器中找到 "search_hotlist" 对应的 Skill
    4. 调用 skill.execute(db, keyword="AI")
    5. 返回结果
    """

    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def execute(
        self,
        function_name: str,
        function_args_json: str,
        db: Session,
        task_id: int | None = None,
        agent_name: str | None = None,
        allowed_function_names: Collection[str] | None = None,
    ) -> str:
        """
        执行 Function Call
        
        参数：
            function_name: 要调用的函数名（如 "search_hotlist"）
            function_args_json: 参数的 JSON 字符串（模型生成的）
            db: 数据库会话
            task_id: 当前任务ID（用于写日志）
            agent_name: 调用方Agent名称（用于写日志）
            allowed_function_names: 当前 Agent 被授权调用的函数名；None 表示非 Agent
                场景沿用注册器权限，保持现有直接调用兼容性
        
        返回：
            str: 执行结果的 JSON 字符串（返回给模型的格式）
        """
        start_time = time.time()

        # 1. Agent 调用必须先过服务端 allowlist，不能只相信模型看到的 tools 列表。
        if (
            allowed_function_names is not None
            and function_name not in allowed_function_names
        ):
            error_result = skill_fail(
                f"未授权的函数: {function_name}，当前 Agent 无权调用"
            )
            logger.warning(
                f"Skill 调用被拒绝: agent={agent_name or 'unknown'}, "
                f"function={function_name}"
            )
            return json.dumps(error_result, ensure_ascii=False)

        # 2. 找到对应的 Skill
        skill = self.registry.get(function_name)
        if not skill:
            error_result = skill_fail(f"未知的函数: {function_name}，请检查函数名是否正确")
            logger.error(f"Skill 未找到: {function_name}")
            return json.dumps(error_result, ensure_ascii=False)

        # 3. 解析参数（JSON字符串 → Python dict）
        try:
            args = json.loads(function_args_json) if function_args_json else {}
        except json.JSONDecodeError as e:
            error_result = skill_fail(
                f"参数解析失败: {str(e)}，原始参数: {function_args_json}"
            )
            logger.error(f"Skill 参数解析失败: {function_name}, args: {function_args_json}")
            return json.dumps(error_result, ensure_ascii=False)

        # 4. 执行 Skill
        try:
            logger.info(f"执行 Skill: {function_name}, args: {args}")
            raw_result = skill.execute(db=db, **args)
            duration_ms = (time.time() - start_time) * 1000
            result = normalize_skill_result(raw_result, function_name, duration_ms)
            logger.info(f"Skill 执行完成: {function_name}, 耗时: {duration_ms:.0f}ms")

            skill_status = "success" if result.get("success") else "failed"
            if task_id and agent_name:
                _save_agent_log(
                    db=db,
                    task_id=task_id,
                    agent_name=agent_name,
                    skill_name=function_name,
                    skill_input=args,
                    skill_output=result,
                    status=skill_status,
                    duration_seconds=round(duration_ms / 1000, 3),
                    error_message=result.get("error") if not result.get("success") else None,
                )
                write_audit_log(
                    db,
                    task_id,
                    "skill",
                    function_name,
                    agent_name=agent_name,
                    input_summary=_truncate_dict(args),
                    output_summary=_truncate_dict({
                        "success": result.get("success"),
                        "error": result.get("error"),
                        "meta": result.get("meta"),
                        "passed": result.get("passed"),
                    }),
                    status=skill_status,
                    duration_ms=duration_ms,
                    error_message=result.get("error") if not result.get("success") else None,
                )

            return json.dumps(result, ensure_ascii=False)

        except Exception as e:
            duration = round(time.time() - start_time, 3)
            error_msg = str(e)
            logger.exception(f"Skill 执行异常: {function_name}, error: {error_msg}")

            # 写失败日志
            if task_id and agent_name:
                _save_agent_log(
                    db=db,
                    task_id=task_id,
                    agent_name=agent_name,
                    skill_name=function_name,
                    skill_input=args,
                    skill_output=None,
                    status="failed",
                    duration_seconds=duration,
                    error_message=error_msg,
                )
                write_audit_log(
                    db,
                    task_id,
                    "skill",
                    function_name,
                    agent_name=agent_name,
                    input_summary=_truncate_dict(args),
                    status="failed",
                    duration_ms=duration * 1000,
                    error_message=error_msg,
                )

            error_result = skill_fail(f"Skill 执行失败: {error_msg}")
            return json.dumps(error_result, ensure_ascii=False)


def _truncate_dict(data: dict | None, max_str: int = 500) -> dict | None:
    """审计日志用：截断过长字符串，避免单条过大。"""
    if not data:
        return data
    out: dict = {}
    for key, value in data.items():
        if isinstance(value, str) and len(value) > max_str:
            out[key] = value[:max_str] + "…"
        elif isinstance(value, dict):
            out[key] = _truncate_dict(value, max_str)
        else:
            out[key] = value
    return out


def _save_agent_log(
    db: Session,
    task_id: int,
    agent_name: str,
    skill_name: str,
    skill_input: dict,
    skill_output: dict | None,
    status: str,
    duration_seconds: float,
    error_message: str | None = None,
) -> None:
    """写 Agent 执行日志到数据库（内部辅助函数）"""
    try:
        from app.models.agent_log import AgentLog
        log = AgentLog(
            task_id=task_id,
            agent_name=agent_name,
            skill_name=skill_name,
            skill_input=skill_input,
            skill_output=skill_output,
            status=status,
            duration_seconds=duration_seconds,
            error_message=error_message,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"写 AgentLog 失败: {e}")
