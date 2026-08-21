"""独立 Agent 任务 Worker：消费数据库持久队列。"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models.task_execution_job import TaskExecutionJob
from app.services.task_execution_queue import process_one_task_execution_job
from app.utils.logger import logger, setup_logger


def _configure_utf8_streams(*streams: object) -> None:
    """避免 Windows 默认 GBK 控制台因日志中的 Unicode 字符而报错。"""
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def execute_job(job: TaskExecutionJob) -> None:
    """把持久 Job 分发到现有编排入口。"""
    from app.api.v1.tasks import _resume_task_background, _run_agents_background

    if job.job_type == "start":
        _run_agents_background(job.task_id)
        return
    if job.job_type == "resume":
        action = str(dict(job.payload or {}).get("action") or "retry")
        _resume_task_background(job.task_id, action)
        return
    raise ValueError(f"不支持的任务执行类型: {job.job_type}")


def run_once(*, worker_id: str, lease_seconds: int, max_attempts: int) -> bool:
    db = SessionLocal()
    try:
        return process_one_task_execution_job(
            db,
            worker_id=worker_id,
            execute=execute_job,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            retry_delay_seconds=5,
        )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="消费持久 Agent 任务队列")
    parser.add_argument("--once", action="store_true", help="最多处理一个 Job 后退出")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--lease-seconds", type=int, default=900)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()

    _configure_utf8_streams(sys.stdout, sys.stderr)
    setup_logger()
    worker_id = _worker_id()
    logger.info(f"任务 Worker 启动: worker_id={worker_id}")
    while True:
        processed = run_once(
            worker_id=worker_id,
            lease_seconds=max(60, args.lease_seconds),
            max_attempts=max(1, args.max_attempts),
        )
        if args.once:
            return
        if not processed:
            time.sleep(max(0.1, args.poll_seconds))


if __name__ == "__main__":
    main()
