"""
安全模块 - JWT 和密码哈希
=========================
这是整个用户鉴权的核心，负责两件事：
1. 密码安全：用 bcrypt 哈希存储密码，验证密码
2. JWT 令牌：生成登录 Token，验证 Token 有效性

【关键概念】JWT（JSON Web Token）是什么？
-------------------------------------------
用户登录成功后，服务器不再保存"登录状态"（无状态设计）。
而是生成一个加密的"通行证"（Token）给用户。
用户每次请求时带上这个 Token，服务器验证签名后知道"这是谁"。

Token 结构（三段用.分隔）：
  header.payload.signature
  - header: 算法信息（如 {"alg":"HS256"}）
  - payload: 用户数据（如 {"sub":"123","exp":1234567890}）
  - signature: 用 SECRET_KEY 对前两段的签名（防伪造）

【关键概念】bcrypt 为什么比 md5/sha256 安全？
------------------------------------------------
- MD5/SHA256：极快，黑客用"彩虹表"可以反查
- bcrypt：故意设计得慢（每次哈希要0.1-1秒），且加了随机"盐"
  即使两个用户密码相同，存储的哈希值也不同
  暴力破解一亿个密码需要几十年
"""

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings


# ====================================================
# 密码哈希工具
# ====================================================

# CryptContext 是密码哈希的"上下文管理器"
# schemes=["bcrypt"]：使用 bcrypt 算法
# deprecated="auto"：如果用了旧算法，自动标记为需要升级
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    将明文密码哈希化
    
    每次调用结果都不同（因为 bcrypt 每次生成不同的随机盐），
    但 verify_password 依然能验证正确性
    
    示例：
        hash_password("123456") -> "$2b$12$K0Q...（60位随机字符）"
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码是否正确
    
    原理：bcrypt 把"盐"存在了哈希值里，
    所以能从 hashed_password 提取盐重新计算，再比对结果
    
    示例：
        verify_password("123456", "$2b$12$K0Q...") -> True
        verify_password("wrong", "$2b$12$K0Q...") -> False
    """
    return pwd_context.verify(plain_password, hashed_password)


# ====================================================
# JWT 令牌操作
# ====================================================

def create_access_token(
    subject: str | int,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    生成 JWT 访问令牌
    
    参数：
        subject: 令牌主题，通常是用户ID（str格式）
        expires_delta: 过期时间，不传则使用配置中的默认值
    
    返回：
        JWT 字符串（如 "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.xxx"）
    
    示例：
        token = create_access_token(subject="42")
        # 用户登录时返回这个 token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    # payload 是 JWT 中间段的内容（可以被 base64 解码，不要存敏感信息）
    payload = {
        "sub": str(subject),  # subject：令牌的主体（用户ID）
        "exp": expire,        # expiration time：过期时间
        "iat": datetime.utcnow(),  # issued at：签发时间
        "type": "access",    # 自定义字段：令牌类型
    }

    # 用 SECRET_KEY 对 payload 签名生成最终 JWT
    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[str]:
    """
    解码 JWT 令牌，返回用户ID（subject字段）
    
    验证步骤（jose库自动完成）：
    1. 验证签名：用 SECRET_KEY 重新计算签名，和 token 中的签名比对
    2. 验证过期：检查 exp 字段是否超过当前时间
    3. 如果都通过，返回 payload 中的数据
    
    返回：
        str: 用户ID（成功时）
        None: 令牌无效或已过期
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            return None
        return user_id
    except JWTError:
        # 签名错误 / 过期 / 格式错误 都会抛出 JWTError
        return None
