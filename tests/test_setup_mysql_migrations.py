"""MySQL 增量迁移执行器测试。"""

from unittest.mock import MagicMock

from scripts.setup_mysql import (
    _expand_guarded_add_columns,
    _initialize_schema,
    _mysql_migration_lock,
)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


def test_mysql_migration_lock_serializes_schema_changes():
    connection = MagicMock()
    connection.execute.side_effect = [_ScalarResult(1), _ScalarResult(1)]

    with _mysql_migration_lock(connection, timeout_seconds=5):
        pass

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert "GET_LOCK" in statements[0]
    assert "RELEASE_LOCK" in statements[1]


def test_mysql_migration_lock_fails_when_another_runner_owns_it():
    connection = MagicMock()
    connection.execute.return_value = _ScalarResult(0)

    try:
        with _mysql_migration_lock(connection, timeout_seconds=0):
            raise AssertionError("lock body must not run")
    except RuntimeError as exc:
        assert "迁移锁" in str(exc)
    else:
        raise AssertionError("expected migration lock failure")


def test_expand_guarded_add_columns_skips_existing_columns():
    statement = """
    ALTER TABLE tasks
      ADD COLUMN IF NOT EXISTS execution_status VARCHAR(30) NOT NULL DEFAULT 'queued',
      ADD COLUMN IF NOT EXISTS content_status VARCHAR(30) NOT NULL DEFAULT 'brief_missing',
      ADD COLUMN IF NOT EXISTS status_reason TEXT NULL
    """

    expanded = _expand_guarded_add_columns(
        statement,
        column_exists=lambda table, column: (table, column)
        == ("tasks", "content_status"),
    )

    assert expanded == [
        "ALTER TABLE tasks ADD COLUMN execution_status VARCHAR(30) NOT NULL DEFAULT 'queued'",
        "ALTER TABLE tasks ADD COLUMN status_reason TEXT NULL",
    ]


def test_expand_guarded_add_columns_preserves_regular_statements():
    statement = "CREATE TABLE IF NOT EXISTS example (id INT PRIMARY KEY)"

    assert _expand_guarded_add_columns(
        statement,
        column_exists=lambda _table, _column: False,
    ) == [statement]


def test_schema_initialization_locks_create_all_and_migrations():
    connection = MagicMock()
    events = []

    _initialize_schema(
        connection,
        create_all=lambda bind: events.append(("create", bind)),
        apply_migrations=lambda bind: events.append(("migrate", bind)),
    )

    assert events == [("create", connection), ("migrate", connection)]
