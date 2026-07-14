"""
Reflexion 反思服务测试
"""

from unittest.mock import patch

from app.services.reflect_service import reflect_on_step_failure


def test_reflect_fallback_when_llm_unavailable():
    state = {
        "raw_requirement": "写一篇 AI 就业微博，300字",
        "platform": "weibo",
        "copy_content": "太短",
        "verification": {
            "passed": False,
            "failed_checks": ["length_ok"],
            "reason": "字数不足",
        },
        "plan": {"steps": [{"stage": "verify", "step_id": "verify_draft"}]},
        "current_step": 3,
        "reflect_count": 0,
    }
    with patch("app.services.reflect_service.get_deepseek_client", side_effect=RuntimeError("no api")):
        result = reflect_on_step_failure(state, stage="verify")

    assert result["rewrite_hint"]
    assert "字数" in result["rewrite_hint"] or "重写" in result["rewrite_hint"]
    assert result.get("context_append")
    assert result["source"] in ("rules", "rules_fallback")


@patch("app.services.reflect_service.get_deepseek_client")
def test_reflect_parses_planner_json(mock_client):
    mock_response = mock_client.return_value.chat.completions.create.return_value
    mock_response.choices = [
        type("Choice", (), {
            "message": type("Msg", (), {
                "content": '{"summary":"主题偏离","rewrite_hint":"围绕AI就业重写","focus":"topic"}'
            })()
        })()
    ]

    state = {
        "raw_requirement": "AI就业",
        "platform": "weibo",
        "copy_content": "今天天气不错",
        "verification": {"passed": False},
        "plan": {"steps": [{"stage": "verify"}]},
        "current_step": 0,
        "reflect_count": 1,
    }
    result = reflect_on_step_failure(state, stage="verify")

    assert result["source"] == "planner"
    assert "AI就业" in result["rewrite_hint"] or "重写" in result["rewrite_hint"]
    assert "Reflexion 第2轮" in result["context_append"]


def test_handle_step_outcome_triggers_reflect():
    from app.agents.agentic_runners import handle_step_outcome

    state = {
        "task_id": 1,
        "db": None,
        "last_step_failed": True,
        "retry_count": 99,
        "reflect_count": 0,
        "plan": {
            "steps": [
                {"stage": "requirement", "step_id": "req"},
                {"stage": "copywriter", "step_id": "copy"},
                {"stage": "verify", "step_id": "verify"},
            ]
        },
        "current_step": 2,
        "raw_requirement": "AI就业",
        "platform": "weibo",
        "verification": {"passed": False, "failed_checks": ["topic_match"]},
        "context_messages": [],
    }

    with patch("app.agents.agentic_runners.reflect_on_step_failure") as mock_reflect:
        mock_reflect.return_value = {
            "summary": "跑题",
            "rewrite_hint": "紧扣 AI 就业",
            "focus": "topic",
            "source": "planner",
            "context_append": "[Reflexion] 紧扣 AI 就业",
        }
        with patch("app.agents.agentic_runners.write_audit_log"):
            updates = handle_step_outcome(state)

    assert updates["current_step"] == 1
    assert updates["reflect_count"] == 1
    assert updates["rewrite_hint"] == "紧扣 AI 就业"
    mock_reflect.assert_called_once()
