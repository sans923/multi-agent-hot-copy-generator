"""
用户鉴权接口（/api/v1/auth）
==============================
提供：
- POST /register  用户注册
- POST /login     用户登录（返回 JWT）
- GET  /me        获取当前登录用户信息
- POST /logout    登出（客户端清除 Token 即可）

【接口设计思路】
注册 -> 创建用户（密码哈希存储）
登录 -> 验证密码 -> 生成 JWT -> 返回给客户端
后续请求 -> 客户端在 Header 中携带 Token -> 服务端验证

【HTTP状态码规范】
200 OK：操作成功
201 Created：创建成功
400 Bad Request：请求参数有误
401 Unauthorized：未登录或 Token 无效
403 Forbidden：已登录但没有权限
404 Not Found：资源不存在
409 Conflict：冲突（如用户名已存在）
422 Unprocessable Entity：请求体格式正确但内容不符合规则（FastAPI默认校验失败）
500 Internal Server Error：服务器内部错误
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, TokenResponse, UserLogin
from app.schemas.common import ApiResponse
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_active_user
from app.config import settings
from app.utils.logger import logger


# APIRouter 类似 Django 的 urls.py，把相关接口分组
# prefix：这个路由下所有接口都以 /auth 开头
# tags：Swagger 文档中的分组标签
router = APIRouter(prefix="/auth", tags=["用户鉴权"])


@router.post(
    "/register",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
    description="注册新账号，用户名和邮箱唯一"
)
def register(
    user_data: UserCreate,      # 请求体自动解析和校验（Pydantic做的）
    db: Session = Depends(get_db)  # 自动注入数据库会话
) -> ApiResponse[UserResponse]:
    """
    注册流程：
    1. 检查用户名是否已存在
    2. 检查邮箱是否已注册
    3. 哈希密码
    4. 创建用户记录
    5. 提交数据库
    6. 返回用户信息（不含密码）
    """
    # 检查用户名唯一性
    existing_user = db.query(User).filter(
        User.username == user_data.username
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"用户名 '{user_data.username}' 已被注册"
        )

    # 检查邮箱唯一性
    existing_email = db.query(User).filter(
        User.email == user_data.email
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"邮箱 '{user_data.email}' 已被注册"
        )

    # 创建新用户（密码哈希化后存储）
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),  # 绝不存明文密码！
        nickname=user_data.nickname or user_data.username,
    )

    db.add(new_user)        # 把对象加入会话（此时还没写数据库）
    db.commit()             # 提交事务（真正写入数据库）
    db.refresh(new_user)    # 刷新对象（获取数据库生成的 id、created_at 等）

    logger.info(f"新用户注册成功: id={new_user.id} username={new_user.username}")

    return ApiResponse(
        success=True,
        message="注册成功",
        data=UserResponse.model_validate(new_user)
    )


@router.post(
    "/login",
    response_model=ApiResponse[TokenResponse],
    summary="用户登录",
    description="邮箱 + 密码登录，返回 JWT 访问令牌"
)
def login(
    login_data: UserLogin,
    db: Session = Depends(get_db)
) -> ApiResponse[TokenResponse]:
    """
    登录流程：
    1. 用邮箱查找用户
    2. 验证密码
    3. 检查账号状态
    4. 生成 JWT Token
    5. 返回 Token
    
    安全注意：
    - 用户不存在和密码错误返回相同的错误信息（防止用户枚举攻击）
    """
    # 查找用户（用邮箱）
    user = db.query(User).filter(User.email == login_data.email).first()

    # 故意不区分"用户不存在"和"密码错误"（防枚举攻击）
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码不正确",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用，请联系管理员"
        )

    # 生成 JWT Token
    access_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    logger.info(f"用户登录成功: id={user.id} username={user.username}")

    return ApiResponse(
        success=True,
        message="登录成功",
        data=TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            user=UserResponse.model_validate(user)
        )
    )


@router.post(
    "/login/form",
    response_model=ApiResponse[TokenResponse],
    summary="表单登录（Swagger测试用）",
    description="支持 OAuth2 标准表单登录，主要用于 Swagger UI 的 Authorize 按钮"
)
def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
) -> ApiResponse[TokenResponse]:
    """
    OAuth2PasswordRequestForm 是 FastAPI 内置的表单解析器
    接收 username（这里用邮箱）和 password 两个表单字段
    
    这个接口主要用于 Swagger UI 的 "Authorize" 按钮，
    实际前端开发建议用上面的 /login JSON 接口
    """
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码不正确",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用"
        )

    access_token = create_access_token(subject=user.id)

    return ApiResponse(
        success=True,
        message="登录成功",
        data=TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            user=UserResponse.model_validate(user)
        )
    )


@router.get(
    "/me",
    response_model=ApiResponse[UserResponse],
    summary="获取当前用户信息",
    description="需要登录才能访问，返回当前登录用户的详细信息"
)
def get_me(
    current_user: User = Depends(get_current_active_user)
    # Depends(get_current_active_user)：这是依赖注入
    # FastAPI 自动：提取Token -> 验证Token -> 查用户 -> 传入 current_user
) -> ApiResponse[UserResponse]:
    """验证当前 Token 是否有效，并返回用户信息"""
    return ApiResponse(
        success=True,
        message="获取成功",
        data=UserResponse.model_validate(current_user)
    )


@router.post(
    "/logout",
    response_model=ApiResponse,
    summary="用户登出",
    description="JWT 无状态，服务端无法主动使 Token 失效。客户端删除 Token 即完成登出。"
)
def logout(
    current_user: User = Depends(get_current_active_user)
) -> ApiResponse:
    """
    JWT 登出说明：
    由于 JWT 是无状态的，服务端无法"销毁"一个有效的 Token。
    真正的登出需要客户端删除本地存储的 Token。
    
    如果需要强制登出（如修改密码后使旧Token失效），
    可以在 Phase 4 引入 Redis 黑名单机制
    """
    logger.info(f"用户登出: id={current_user.id} username={current_user.username}")
    return ApiResponse(success=True, message="登出成功，请删除本地Token")
