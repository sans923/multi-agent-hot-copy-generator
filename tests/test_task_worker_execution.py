from types import SimpleNamespace

import pytest

from scripts import task_worker


def test_worker_retries_when_orchestration_returns_failure(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.tasks._run_agents_background",
        lambda _task_id: {"success": False, "error": "LLM unavailable"},
    )
    job = SimpleNamespace(job_type="start", task_id=42, payload={})

    with pytest.raises(task_worker.RetryableTaskExecutionError, match="LLM unavailable"):
        task_worker.execute_job(job)


def test_worker_accepts_explicit_awaiting_human_result(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.tasks._run_agents_background",
        lambda _task_id: {"success": False, "awaiting_human": True},
    )
    job = SimpleNamespace(job_type="start", task_id=42, payload={})

    task_worker.execute_job(job)
