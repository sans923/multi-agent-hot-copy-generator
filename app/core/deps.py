"""
FastAPI 依赖注入模块
===================
依赖注入（Dependency Injection）是 FastAPI 最强大的特性之一

【什么是依赖注入？】
不需要在每个路由函数里重复写"验证Token、查用户"的代码，
而是定义一次"依赖"，在需要的路由上声明使用它，FastAPI 自动执行。

类比：就像餐厅不需要每桌自备刀叉，而是由服务员（FastAPI）
把刀叉（数据库会话、当前用户）送到你面前。

用法示例：
    @router.get("/profile")
    def get_profile(current_user: User = Depends(get_current_user)):
        return current_user  # FastAPI 自动把当前登录用户传进来

【执行顺序】
1. 请求到达路由
2. FastAPI 发现有 Depends(get_current_user)
3. 先执行 get_current_user（它又依赖 get_db）
4. 把结果传给路由函数
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import decode_access_token
from app.models.user import User


# HTTPBearer：从请求头 "Authorization: Bearer <token>" 中提取 token
# 比 OAuth2PasswordBearer 更简单，Swagger UI 里只显示一个直接粘贴 token 的输入框
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    从 JWT Token 中提取当前登录用户

    工作流程：
    1. bearer_scheme 从请求头提取 token 字符串
    2. decode_access_token 验证并解码 token，得到用户ID
    3. 用用户ID查数据库得到 User 对象
    4. 返回 User 对象给路由函数使用
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的身份凭证，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    token = credentials.credentials
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    在 get_current_user 基础上，额外检查账号是否被封禁
    
    大多数接口应该用这个依赖而不是 get_current_user，
    因为被封禁的用户虽然 Token 有效，但不应该能继续操作
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用，请联系管理员"
        )
    return current_user


def get_current_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    只允许管理员访问的接口使用此依赖
    
    依赖链：get_current_admin_user
              -> get_current_active_user
                 -> get_current_user
                    -> oauth2_scheme（提取token）
                    -> get_db（获取数据库会话）
    FastAPI 会自动解析这个依赖链并按顺序执行
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return current_user
