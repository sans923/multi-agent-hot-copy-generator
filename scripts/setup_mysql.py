"""
MySQL 初始化：测试连接并创建所有表

用法：
    python scripts/setup_mysql.py
"""
import sys
import os
from contextlib import contextmanager
from pathlib import Path
import re
from collections.abc import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.config import settings
from app.database import engine, create_tables


_MIGRATION_LOCK_NAME = "hot_copy_generator_schema_migrations"


def _expand_guarded_add_columns(
    statement: str,
    column_exists: Callable[[str, str], bool],
) -> list[str]:
    """将 MySQL 不支持的 ADD COLUMN IF NOT EXISTS 展开为可执行语句。"""
    alter_match = re.match(
        r"^\s*ALTER\s+TABLE\s+`?(\w+)`?\s+(.+)$",
        statement,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not alter_match or "ADD COLUMN IF NOT EXISTS" not in statement.upper():
        return [statement]

    table_name, alter_body = alter_match.groups()
    clauses = re.split(
        r",\s*(?=ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS)",
        alter_body,
        flags=re.IGNORECASE,
    )
    expanded: list[str] = []
    for clause in clauses:
        column_match = re.match(
            r"^\s*ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+`?(\w+)`?\s+(.+?)\s*$",
            clause,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not column_match:
            return [statement]
        column_name, definition = column_match.groups()
        if not column_exists(table_name, column_name):
            expanded.append(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )
    return expanded


def _mysql_column_exists(connection, table_name: str, column_name: str) -> bool:
    count = connection.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar_one()
    return count > 0


@contextmanager
def _mysql_migration_lock(connection, timeout_seconds: int = 60):
    """串行化同一 MySQL 实例上的轻量迁移，避免并发 DDL 竞态。"""
    acquired = connection.execute(
        text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
        {"lock_name": _MIGRATION_LOCK_NAME, "timeout_seconds": timeout_seconds},
    ).scalar_one()
    if acquired != 1:
        raise RuntimeError("无法获取 MySQL 数据库迁移锁，请稍后重试")

    try:
        yield
    finally:
        connection.execute(
            text("SELECT RELEASE_LOCK(:lock_name)"),
            {"lock_name": _MIGRATION_LOCK_NAME},
        )


def apply_schema_migrations() -> None:
    """执行可重入的轻量 MySQL 迁移；正式生产应迁移到 Alembic。"""
    with engine.begin() as connection:
        with _mysql_migration_lock(connection):
            for migration_name in (
                "migrate_memory_index_lock.sql",
                "migrate_content_production_p0.sql",
                "migrate_content_production_p1.sql",
                "migrate_content_production_p2.sql",
                "migrate_task_execution_queue.sql",
            ):
                migration_path = Path(__file__).with_name(migration_name)
                sql = "\n".join(
                    line
                    for line in migration_path.read_text(encoding="utf-8").splitlines()
                    if not line.lstrip().startswith("--")
                )
                statements = [
                    statement.strip()
                    for statement in sql.split(";")
                    if statement.strip()
                ]
                for statement in statements:
                    expanded_statements = _expand_guarded_add_columns(
                        statement,
                        column_exists=lambda table_name, column_name: _mysql_column_exists(
                            connection, table_name, column_name
                        ),
                    )
                    for expanded_statement in expanded_statements:
                        connection.exec_driver_sql(expanded_statement)


def main() -> None:
    print("=" * 50)
    print("MySQL 初始化")
    print("=" * 50)
    # 隐藏密码
    url = settings.DATABASE_URL
    if "@" in url:
        prefix, rest = url.split("@", 1)
        if ":" in prefix:
            scheme_user = prefix.rsplit(":", 1)[0]
            print(f"连接: {scheme_user}:****@{rest}")
        else:
            print(f"连接: {url}")
    else:
        print(f"连接: {url}")

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[OK] 数据库连接成功")
    except Exception as e:
        print(f"[失败] 无法连接 MySQL: {e}")
        print("\n请确认：")
        print("  1. MySQL 服务已启动")
        print("  2. 已执行 scripts/init_mysql.sql 创建库和用户")
        print("  3. .env 中 MYSQL_* 或 DATABASE_URL 配置正确")
        sys.exit(1)

    create_tables()
    print("[OK] 数据表创建完成")
    apply_schema_migrations()
    print("[OK] 数据库增量迁移完成")
    print("\n可运行 python run.py 启动后端。")


if __name__ == "__main__":
    main()
