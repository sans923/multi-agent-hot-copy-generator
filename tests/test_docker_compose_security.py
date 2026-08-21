from pathlib import Path


def test_compose_requires_database_passwords_without_hardcoded_defaults():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "copygen123" not in compose
    assert "rootpass" not in compose
    assert "${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}" in compose
    assert "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}" in compose
    assert "$${MYSQL_PASSWORD}" in compose
