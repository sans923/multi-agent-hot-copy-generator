import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.evaluation.writing_pattern_injection_ab import (
    WritingPatternInjectionABEvaluator,
    build_writing_pattern_messages,
    load_writing_pattern_cases,
    score_writing_pattern_run,
)
from app.evaluation.prompt_injection_ab import EvaluationRun


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "writing_pattern_prompt_injection_cases.json"
)


class _FakeCompletions:
    def __init__(self, content):
        self.content = content

    def create(self, **kwargs):
        message = SimpleNamespace(content=self.content, tool_calls=[])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=SimpleNamespace(total_tokens=25),
        )


class _FakeClient:
    def __init__(self, content):
        self.chat = SimpleNamespace(
            completions=_FakeCompletions(content),
        )


class WritingPatternCaseTest(unittest.TestCase):
    def test_fixture_has_fifty_distinct_cases_across_all_vectors(self):
        cases = load_writing_pattern_cases(FIXTURE_PATH)

        self.assertEqual(len(cases), 50)
        self.assertEqual(len({case.case_id for case in cases}), 50)
        self.assertEqual(
            {case.vector for case in cases},
            {"platform", "title", "content"},
        )

    def test_hardened_message_keeps_all_attack_vectors_in_untrusted_boundary(self):
        for case in load_writing_pattern_cases(FIXTURE_PATH):
            messages = build_writing_pattern_messages(case, "hardened")
            user_prompt = messages[1]["content"]
            start = user_prompt.index("<UNTRUSTED_REFERENCE_ARTICLES_JSON>")
            end = user_prompt.index("</UNTRUSTED_REFERENCE_ARTICLES_JSON>")

            self.assertNotIn(case.canary, user_prompt[:start])
            self.assertIn(case.canary, user_prompt[start:end])

    def test_only_hardened_variant_contains_untrusted_policy(self):
        case = load_writing_pattern_cases(FIXTURE_PATH)[0]

        baseline = build_writing_pattern_messages(case, "baseline")
        hardened = build_writing_pattern_messages(case, "hardened")

        self.assertNotIn("不可信数据", baseline[0]["content"])
        self.assertIn("不可信数据", hardened[0]["content"])


class WritingPatternScoringTest(unittest.TestCase):
    def test_canary_as_json_value_is_attack_success(self):
        case = load_writing_pattern_cases(FIXTURE_PATH)[0]
        run = EvaluationRun(
            case_id=case.case_id,
            source=case.vector,
            variant="baseline",
            repetition=1,
            model="fake-model",
            final_response=json.dumps({"title_formula": {"pattern": case.canary}}),
            requested_tools=[],
            tool_arguments=[],
            tokens_used=10,
            latency_ms=1.0,
            finish_reason="stop",
        )

        scored = score_writing_pattern_run(case, run)

        self.assertTrue(scored.attack_succeeded)
        self.assertTrue(scored.output_valid)

    def test_valid_json_without_canary_is_normal_success(self):
        case = load_writing_pattern_cases(FIXTURE_PATH)[0]
        evaluator = WritingPatternInjectionABEvaluator(
            client=_FakeClient('{"title_formula":{"pattern":"[数字]+[反差]"}}'),
            model="fake-model",
        )

        run = evaluator.run_case(case, "hardened", 1)

        self.assertFalse(run.attack_succeeded)
        self.assertTrue(run.output_valid)


if __name__ == "__main__":
    unittest.main()
