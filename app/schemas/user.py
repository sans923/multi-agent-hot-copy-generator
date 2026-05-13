"""
用户相关 Pydantic 数据模型（Schemas）
=====================================
【Schema vs Model 的区别】
- Model（SQLAlchemy）：定义数据库表结构，负责存储
- Schema（Pydantic）：定义 API 的输入/输出格式，负责校验和序列化

为什么需要 Schema？
- 防止用户乱传参数（如把 hashed_password 直接传进来）
- 自动验证类型（age 传了字符串"abc"会报错）
- 自动生成 Swagger API 文档
- 控制哪些字段对外暴露（hashed_password 绝对不能出现在响应里）

命名规范：
- UserCreate：创建用户时的请求体格式
- UserLogin：登录时的请求体格式
- UserResponse：返回给客户端的用户信息格式（不含密码！）
- UserUpdate：更新用户信息时的请求体格式
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, Field


class UserCreate(BaseModel):
    """
    注册新用户的请求体
    
    使用示例（前端发送的 JSON）：
    {
        "username": "zhangsan",
        "email": "zhangsan@example.com",
        "password": "Abc123456"
    }
    """
    username: str = Field(
        min_length=3,
        max_length=50,
        description="用户名，3-50个字符",
        examples=["zhangsan"]
    )
    email: EmailStr = Field(
        description="邮箱地址",
        examples=["zhangsan@example.com"]
    )
    password: str = Field(
        min_length=6,
        max_length=72,
        description="密码，6-72位（bcrypt算法最大支持72字节）",
        examples=["Abc123456"]
    )
    nickname: Optional[str] = Field(
        default=None,
        max_length=50,
        description="昵称（可选）"
    )

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """
        密码强度校验
        实际项目可以加更严格的规则（大小写混合、包含数字等）
        这里校验不含空格，并检查 bcrypt 的字节长度上限
        """
        if " " in v:
            raise ValueError("密码不能包含空格")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码不能超过72字节（中文等多字节字符每个占2-4字节，请缩短密码）")
        return v

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        """用户名只能包含字母、数字、下划线"""
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v.lower()  # 统一转小写，避免大小写混淆


class UserLogin(BaseModel):
    """
    登录请求体（支持用邮箱或用户名登录）
    
    注意：这个 Schema 主要给 JSON Body 请求用
    FastAPI 内置的 OAuth2 表单登录用 OAuth2PasswordRequestForm
    """
    email: EmailStr = Field(description="登录邮箱")
    password: str = Field(description="登录密码")


class UserResponse(BaseModel):
    """
    返回给客户端的用户信息（安全版本，不含密码！）
    
    这是 API 响应时的格式，只暴露安全的字段
    """
    id: int
    username: str
    email: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        """
        from_attributes=True（旧版叫 orm_mode=True）
        允许从 SQLAlchemy ORM 对象直接转换为 Pydantic 模型
        
        没有这个配置，UserResponse(**user.__dict__) 才能工作，
        有了它，直接 UserResponse.model_validate(user) 即可
        """
        from_attributes = True


class UserUpdate(BaseModel):
    """更新用户信息（所有字段都是可选的，只更新传了的字段）"""
    nickname: Optional[str] = Field(default=None, max_length=50)
    avatar_url: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=72)


class TokenResponse(BaseModel):
    """
    登录成功后返回的 Token 信息
    
    返回示例：
    {
        "access_token": "eyJhbGciOiJIUzI1NiJ9...",
        "token_type": "bearer",
        "expires_in": 1440
    }
    """
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 过期时间（分钟）
    user: UserResponse  # 同时返回用户信息，减少一次额外请求


class TokenData(BaseModel):
    """JWT payload 中的数据（内部使用，不对外）"""
    user_id: Optional[str] = None
