"""与 LangGraph 0.2.x 兼容的参数化 SQLite durable checkpointer。"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)


class ParameterizedSqliteSaver(BaseCheckpointSaver):
    """同步 SQLite saver；所有外部值只通过绑定参数进入 SQL。"""

    def __init__(self, path: str | Path, *, serde=None) -> None:
        super().__init__(serde=serde)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.RLock()
        self._setup()

    def _setup(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    checkpoint_type TEXT NOT NULL,
                    checkpoint BLOB NOT NULL,
                    metadata_type TEXT NOT NULL,
                    metadata BLOB NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                );
                CREATE INDEX IF NOT EXISTS ix_checkpoints_latest
                    ON checkpoints(thread_id, checkpoint_ns, checkpoint_id DESC);
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    write_idx INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    value BLOB NOT NULL,
                    task_path TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (
                        thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx
                    )
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _row_to_tuple(self, row: sqlite3.Row | tuple[Any, ...]) -> CheckpointTuple:
        (
            thread_id,
            checkpoint_ns,
            checkpoint_id,
            parent_checkpoint_id,
            checkpoint_type,
            checkpoint_blob,
            metadata_type,
            metadata_blob,
        ) = row
        with self._lock:
            writes = self._connection.execute(
                """
                SELECT task_id, channel, value_type, value
                FROM checkpoint_writes
                WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                ORDER BY task_id, write_idx
                """,
                (thread_id, checkpoint_ns, checkpoint_id),
            ).fetchall()
        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }
        parent_config = None
        if parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_checkpoint_id,
                }
            }
        return CheckpointTuple(
            config=config,
            checkpoint=self.serde.loads_typed((checkpoint_type, checkpoint_blob)),
            metadata=self.serde.loads_typed((metadata_type, metadata_blob)),
            parent_config=parent_config,
            pending_writes=[
                (task_id, channel, self.serde.loads_typed((value_type, value)))
                for task_id, channel, value_type, value in writes
            ],
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = get_checkpoint_id(config)
        params: tuple[Any, ...]
        if checkpoint_id:
            query = """
                SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                       checkpoint_type, checkpoint, metadata_type, metadata
                FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
            """
            params = (thread_id, checkpoint_ns, checkpoint_id)
        else:
            query = """
                SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                       checkpoint_type, checkpoint, metadata_type, metadata
                FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ?
                ORDER BY checkpoint_id DESC LIMIT 1
            """
            params = (thread_id, checkpoint_ns)
        with self._lock:
            row = self._connection.execute(query, params).fetchone()
        return self._row_to_tuple(row) if row else None

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        del new_versions
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        parent_id = configurable.get("checkpoint_id")
        checkpoint_type, checkpoint_blob = self.serde.dumps_typed(checkpoint)
        metadata_type, metadata_blob = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO checkpoints (
                    thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                    checkpoint_type, checkpoint, metadata_type, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint["id"],
                    parent_id,
                    checkpoint_type,
                    checkpoint_blob,
                    metadata_type,
                    metadata_blob,
                ),
            )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(configurable["checkpoint_id"])
        rows = []
        replace_existing = all(channel in WRITES_IDX_MAP for channel, _ in writes)
        for index, (channel, value) in enumerate(writes):
            value_type, value_blob = self.serde.dumps_typed(value)
            rows.append((
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                task_id,
                WRITES_IDX_MAP.get(channel, index),
                channel,
                value_type,
                value_blob,
                task_path,
            ))
        with self._lock, self._connection:
            statement = """
                INSERT OR {conflict_action} INTO checkpoint_writes (
                    thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx,
                    channel, value_type, value, task_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """.format(conflict_action="REPLACE" if replace_existing else "IGNORE")
            self._connection.executemany(statement, rows)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        if limit is not None and limit <= 0:
            return
        clauses: list[str] = []
        params: list[Any] = []
        if config:
            configurable = config["configurable"]
            clauses.append("thread_id = ?")
            params.append(str(configurable["thread_id"]))
            if "checkpoint_ns" in configurable:
                clauses.append("checkpoint_ns = ?")
                params.append(str(configurable.get("checkpoint_ns", "")))
            if checkpoint_id := get_checkpoint_id(config):
                clauses.append("checkpoint_id = ?")
                params.append(checkpoint_id)
        if before and (before_id := get_checkpoint_id(before)):
            clauses.append("checkpoint_id < ?")
            params.append(before_id)
        query = """
            SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                   checkpoint_type, checkpoint, metadata_type, metadata
            FROM checkpoints
        """
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY checkpoint_id DESC"
        with self._lock:
            rows = self._connection.execute(query, tuple(params)).fetchall()
        yielded = 0
        for row in rows:
            item = self._row_to_tuple(row)
            if filter and not all(item.metadata.get(key) == value for key, value in filter.items()):
                continue
            yield item
            yielded += 1
            if limit is not None and yielded >= limit:
                break

    def delete_thread(self, thread_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM checkpoint_writes WHERE thread_id = ?", (thread_id,)
            )
            self._connection.execute(
                "DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,)
            )
