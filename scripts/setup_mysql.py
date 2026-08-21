"""
MySQL 初始化：测试连接并创建所有表

用法：
    python scripts/setup_mysql.py
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.config import settings
from app.database import engine, create_tables


def apply_schema_migrations() -> None:
    """执行可重入的轻量 MySQL 迁移；正式生产应迁移到 Alembic。"""
    with engine.begin() as connection:
        for migration_name in (
            "migrate_memory_index_lock.sql",
            "migrate_content_production_p0.sql",
            "migrate_content_production_p1.sql",
            "migrate_content_production_p2.sql",
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
                connection.exec_driver_sql(statement)


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
