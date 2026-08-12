import json

from app.skills.base import BaseSkill, SkillExecutor, SkillRegistry


class RecordingSkill(BaseSkill):
    def __init__(self, name: str):
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "测试工具"

    @property
    def parameters_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def execute(self, db, **kwargs) -> dict:
        self.calls += 1
        return {"success": True, "data": {"called": self.name}}


def test_executor_rejects_registered_but_unauthorized_skill():
    registry = SkillRegistry()
    allowed_skill = RecordingSkill("allowed_skill")
    unauthorized_skill = RecordingSkill("unauthorized_skill")
    registry.register(allowed_skill)
    registry.register(unauthorized_skill)
    executor = SkillExecutor(registry)

    result = json.loads(
        executor.execute(
            function_name="unauthorized_skill",
            function_args_json="{}",
            db=None,
            agent_name="test_agent",
            allowed_function_names=["allowed_skill"],
        )
    )

    assert result["success"] is False
    assert "未授权" in result["error"]
    assert unauthorized_skill.calls == 0


def test_executor_runs_skill_in_agent_allowlist():
    registry = SkillRegistry()
    allowed_skill = RecordingSkill("allowed_skill")
    registry.register(allowed_skill)
    executor = SkillExecutor(registry)

    result = json.loads(
        executor.execute(
            function_name="allowed_skill",
            function_args_json="{}",
            db=None,
            allowed_function_names=["allowed_skill"],
        )
    )

    assert result["success"] is True
    assert allowed_skill.calls == 1


def test_executor_keeps_backward_compatible_unscoped_calls():
    registry = SkillRegistry()
    skill = RecordingSkill("legacy_skill")
    registry.register(skill)
    executor = SkillExecutor(registry)

    result = json.loads(
        executor.execute(
            function_name="legacy_skill",
            function_args_json="{}",
            db=None,
        )
    )

    assert result["success"] is True
    assert skill.calls == 1
