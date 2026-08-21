from app.main import _database_url_for_log


def test_database_url_for_log_hides_password():
    safe_url = _database_url_for_log(
        "mysql+pymysql://copygen:secret-password@127.0.0.1:3306/copy_generator"
    )

    assert "secret-password" not in safe_url
    assert "copygen:***@127.0.0.1" in safe_url


def test_database_url_for_log_keeps_sqlite_path():
    assert _database_url_for_log("sqlite:///./data/app.db") == (
        "sqlite:///./data/app.db"
    )
