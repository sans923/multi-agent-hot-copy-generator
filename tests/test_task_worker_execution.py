from types import SimpleNamespace

import pytest

from scripts import task_worker


def test_worker_retries_when_orchestration_returns_failure(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.tasks._run_agents_background",
        lambda _task_id, **_kwargs: {"success": False, "error": "LLM unavailable"},
    )
    job = SimpleNamespace(
        id=1, job_type="start", task_id=42, payload={}, lease_token="lease", attempts=1
    )

    with pytest.raises(task_worker.RetryableTaskExecutionError, match="LLM unavailable"):
        task_worker.execute_job(job)


def test_worker_accepts_explicit_awaiting_human_result(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.tasks._run_agents_background",
        lambda _task_id, **_kwargs: {"success": False, "awaiting_human": True},
    )
    job = SimpleNamespace(
        id=1, job_type="start", task_id=42, payload={}, lease_token="lease", attempts=1
    )

    task_worker.execute_job(job)


def test_worker_forwards_job_fence_to_orchestration(monkeypatch):
    seen = {}

    def run(task_id, **kwargs):
        seen.update(task_id=task_id, **kwargs)
        return {"success": True}

    monkeypatch.setattr("app.api.v1.tasks._run_agents_background", run)
    job = SimpleNamespace(
        id=7,
        job_type="start",
        task_id=42,
        payload={},
        lease_token="lease-7",
        attempts=2,
    )

    task_worker.execute_job(job)

    lease_lost_event = seen.pop("lease_lost_event")
    assert lease_lost_event is None
    assert seen == {
        "task_id": 42,
        "execution_job_id": 7,
        "lease_token": "lease-7",
        "attempt": 2,
    }
