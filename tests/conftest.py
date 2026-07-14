"""
测试公共配置
==============
确保所有 ORM 模型在 create_all 之前注册，避免新增表导致测试库缺表。
"""

import pytest


def pytest_configure():
    """在任何测试模块加载 ORM 前注册全部模型。"""
    import app.models  # noqa: F401


@pytest.fixture(autouse=True)
def _register_all_orm_models():
    import app.models  # noqa: F401
