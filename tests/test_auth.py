"""
Phase 1 鉴权接口测试
=====================
使用 FastAPI 内置的 TestClient（基于 requests 库）
不需要真正启动服务器，直接调用应用处理函数

运行测试：
    # 安装测试依赖（只需一次）
    pip install pytest httpx

    # 在项目根目录运行
    pytest tests/ -v

    # 运行单个测试
    pytest tests/test_auth.py::test_register -v
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db


# ====================================================
# 测试数据库配置（使用内存 SQLite，测试结束后自动清除）
# ====================================================

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """替换正式数据库会话为测试数据库会话"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# 使用依赖覆盖：把 get_db 替换为测试版本
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前创建表，测试后删除（确保测试隔离）"""
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


# TestClient：不需要启动服务器，直接测试
client = TestClient(app)


# ====================================================
# 注册接口测试
# ====================================================

def test_register_success():
    """正常注册"""
    response = client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "password123"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["username"] == "testuser"
    assert "hashed_password" not in data["data"]  # 密码哈希不能出现在响应中！


def test_register_duplicate_username():
    """重复用户名注册应该失败"""
    # 第一次注册
    client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test1@example.com",
        "password": "password123"
    })
    # 第二次用同一个用户名
    response = client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test2@example.com",
        "password": "password123"
    })
    assert response.status_code == 409


def test_register_duplicate_email():
    """重复邮箱注册应该失败"""
    client.post("/api/v1/auth/register", json={
        "username": "user1",
        "email": "same@example.com",
        "password": "password123"
    })
    response = client.post("/api/v1/auth/register", json={
        "username": "user2",
        "email": "same@example.com",
        "password": "password123"
    })
    assert response.status_code == 409


def test_register_short_password():
    """密码太短应该失败（Pydantic校验）"""
    response = client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "123"  # 少于6位
    })
    assert response.status_code == 422


# ====================================================
# 登录接口测试
# ====================================================

def _create_test_user():
    """辅助函数：创建测试用户并返回"""
    client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "password123"
    })


def test_login_success():
    """正常登录"""
    _create_test_user()
    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "password123"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert data["data"]["token_type"] == "bearer"


def test_login_wrong_password():
    """密码错误应该返回 401"""
    _create_test_user()
    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "wrongpassword"
    })
    assert response.status_code == 401


def test_login_nonexistent_user():
    """不存在的用户应该返回 401（不能提示用户不存在，防枚举）"""
    response = client.post("/api/v1/auth/login", json={
        "email": "nobody@example.com",
        "password": "password123"
    })
    assert response.status_code == 401


# ====================================================
# 受保护接口测试
# ====================================================

def test_get_me_with_valid_token():
    """有效 Token 可以访问 /me"""
    _create_test_user()
    login_response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "password123"
    })
    token = login_response.json()["data"]["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "test@example.com"


def test_get_me_without_token():
    """无 Token 应该返回 401"""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_health_check():
    """健康检查接口无需认证"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
