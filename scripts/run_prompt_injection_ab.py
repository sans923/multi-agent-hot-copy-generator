"""运行真实 DeepSeek 提示词注入 A/B 评估。

示例：
    .\.venv-debug\Scripts\python.exe scripts\run_prompt_injection_ab.py --confirm-live
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.requirement_agent import RequirementAgent
from app.config import settings
from app.evaluation.prompt_injection_ab import (
    PromptInjectionABEvaluator,
    load_cases,
    summarize_runs,
)
from app.utils.llm_client import get_deepseek_client


DEFAULT_CASES = PROJECT_ROOT / "tests" / "fixtures" / "prompt_injection_adversarial_cases.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用真实模型比较原始 Prompt 与共享安全契约 Prompt。"
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--model", default=settings.EXECUTOR_MODEL)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="确认将调用真实模型并产生 API token 费用。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_live:
        print("拒绝运行：必须显式传入 --confirm-live，真实评估会产生 API 费用。")
        return 2
    if args.repetitions < 1:
        print("repetitions 必须大于等于 1")
        return 2

    cases = load_cases(args.cases)
    agent = RequirementAgent()
    evaluator = PromptInjectionABEvaluator(
        client=get_deepseek_client(),
        model=args.model,
        role_prompt=agent.system_prompt,
        fake_tool_results={
            "parse_requirement": {
                "success": True,
                "synthetic": True,
                "parsed": {"topic": "智能水杯", "platform": "weibo"},
            },
            "search_hotlist": {
                "success": True,
                "synthetic": True,
                "topics": ["健康饮水", "智能家居"],
            },
        },
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_rounds=args.max_rounds,
    )
    runs = evaluator.run_suite(cases, repetitions=args.repetitions)
    summary = summarize_runs(runs)
    generated_at = datetime.now(timezone.utc).isoformat()
    output = args.output or (
        PROJECT_ROOT
        / "data"
        / "evaluations"
        / f"prompt-injection-ab-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": generated_at,
        "model": args.model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "max_rounds": args.max_rounds,
        "repetitions": args.repetitions,
        "case_count": len(cases),
        "safety": "只使用合成工具；未调用 SkillExecutor；不会写入业务数据库。",
        "summary": summary,
        "runs": [run.to_dict() for run in runs],
    }
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"完整报告：{output}")
    return 0 if all(not run.error for run in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
