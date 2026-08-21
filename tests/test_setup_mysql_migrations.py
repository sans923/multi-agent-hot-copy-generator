"""MySQL 增量迁移执行器测试。"""

from scripts.setup_mysql import _expand_guarded_add_columns


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
