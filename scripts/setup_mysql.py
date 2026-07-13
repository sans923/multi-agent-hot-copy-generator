"""
MySQL 初始化：测试连接并创建所有表

用法：
    python scripts/setup_mysql.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.config import settings
from app.database import engine, create_tables


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
    print("\n可运行 python run.py 启动后端。")


if __name__ == "__main__":
    main()
