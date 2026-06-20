"""
FastAPI 应用主入口
==================
这是整个项目的"心脏"，负责：
1. 创建 FastAPI 应用实例
2. 注册所有路由（各个API接口）
3. 配置全局中间件（跨域、日志、请求追踪）
4. 定义应用生命周期事件（启动/关闭时执行的操作）
5. 配置全局异常处理器

【FastAPI 请求处理流程】
客户端请求
    -> 中间件（CORS检查、日志记录、Token校验）
    -> 路由匹配（找到对应的处理函数）
    -> 依赖注入（自动注入 db session、current_user）
    -> 路由处理函数（执行业务逻辑）
    -> Pydantic 序列化（把返回值转为 JSON）
    -> 中间件（后处理）
    -> 客户端响应
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import time

from app.config import settings
from app.utils.logger import logger, setup_logger
from app.database import create_tables


# ====================================================
# 应用生命周期管理
# ====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理（FastAPI 新版推荐方式，替代旧的 on_event）
    
    yield 之前的代码 = 应用启动时执行（类比 __init__）
    yield 之后的代码 = 应用关闭时执行（类比 __del__，用于清理资源）
    
    这里处理：
    - 启动：初始化日志、创建数据库表
    - 关闭：记录日志（后续可加连接池关闭等）
    """
    # ---- 启动阶段 ----
    setup_logger()  # 必须第一个初始化，后续日志才能正常输出
    logger.info(f"{'='*50}")
    logger.info(f"  {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    logger.info(f"  DEBUG 模式: {settings.DEBUG}")
    logger.info(f"  数据库: {settings.DATABASE_URL}")
    logger.info(f"{'='*50}")

    # 创建所有数据库表（如果不存在）
    # 注意：生产环境应该用 Alembic 迁移，而不是 create_all
    create_tables()

    # 启动 APScheduler 定时任务调度器
    from app.scheduler import start_scheduler, stop_scheduler
    start_scheduler()

    logger.info("应用启动完成，开始处理请求")

    yield  # 应用正常运行中...

    # ---- 关闭阶段 ----
    logger.info("应用正在关闭，清理资源...")
    stop_scheduler()
    logger.info("应用已安全关闭")


# ====================================================
# 创建 FastAPI 应用实例
# ====================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## 多智能体热点爆款文案生成系统 API

基于 3 个 AI Agent 协作，自动抓取热榜话题，生成高质量营销文案。

### Agent 架构
- **需求理解 Agent**：解析用户意图，匹配热点
- **文案创作 Agent**：调用 10 个 Skill 生成初稿
- **审核优化 Agent**：评分并优化文案（最多迭代1次）

### 快速开始
1. 注册账号：`POST /api/v1/auth/register`
2. 登录获取 Token：`POST /api/v1/auth/login`
3. 点击右上角 **Authorize** 按钮，输入 Token
4. 创建生成任务：`POST /api/v1/tasks`
    """,
    openapi_url="/api/openapi.json",     # OpenAPI JSON 规范地址
    docs_url="/docs",                     # Swagger UI 地址
    redoc_url="/redoc",                   # ReDoc 文档地址（更适合阅读）
    lifespan=lifespan,                    # 绑定生命周期管理
    swagger_ui_parameters={
        "persistAuthorization": True,     # 刷新页面后保留 Token，不用重新授权
    },
)


# ====================================================
# 中间件配置
# ====================================================

# CORS（跨域资源共享）中间件
# 允许前端（不同域名/端口）调用后端 API
# 生产环境要把 "*" 改为具体的前端域名！
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://your-production-domain.com"],
    allow_credentials=True,   # 允许携带 Cookie（虽然我们用 JWT 但保留这个选项）
    allow_methods=["*"],       # 允许所有 HTTP 方法（GET/POST/PUT/DELETE等）
    allow_headers=["*"],       # 允许所有请求头（包括 Authorization）
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    请求日志中间件
    记录每个请求的：方法、路径、耗时、响应状态码
    
    这是"切面编程"思想：在不改变业务代码的情况下，
    统一为所有请求添加日志功能
    
    call_next(request) 表示"继续处理请求，等待响应"
    """
    start_time = time.time()

    # 继续处理请求（执行路由函数）
    response = await call_next(request)

    # 计算耗时
    duration_ms = round((time.time() - start_time) * 1000, 2)

    # 根据状态码选择日志级别
    if response.status_code >= 500:
        logger.error(
            f"{request.method} {request.url.path} "
            f"-> {response.status_code} [{duration_ms}ms]"
        )
    elif response.status_code >= 400:
        logger.warning(
            f"{request.method} {request.url.path} "
            f"-> {response.status_code} [{duration_ms}ms]"
        )
    else:
        logger.info(
            f"{request.method} {request.url.path} "
            f"-> {response.status_code} [{duration_ms}ms]"
        )

    return response


# ====================================================
# 全局异常处理器
# ====================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    处理请求参数校验失败的异常
    
    默认 FastAPI 返回的 422 错误格式比较复杂，
    这里统一包装成我们自己的格式，方便前端解析
    
    触发场景：用户传了错误类型的参数（如把字符串传给整数字段）
    """
    # 提取所有错误信息
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append(f"{field}: {error['msg']}")

    logger.warning(f"请求参数校验失败: {errors}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": "请求参数格式错误",
            "data": {"errors": errors}
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    兜底异常处理器：捕获所有未被处理的异常
    
    生产环境不能把内部错误细节暴露给客户端（安全原因），
    所以返回通用错误消息，但在服务端日志里记录详细信息
    """
    logger.exception(f"未处理的异常: {request.method} {request.url.path}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "服务器内部错误，请联系管理员" if not settings.DEBUG
                       else str(exc),
            "data": None
        }
    )


# ====================================================
# 注册路由
# ====================================================

from app.api.v1 import auth, users, hotlist, tasks, logs  # noqa: E402

# include_router 将路由注册到应用
# prefix="/api/v1"：所有 v1 接口都以这个开头
# 完整路径 = /api/v1 + router.prefix + route.path
# 例如：/api/v1/auth/login
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(hotlist.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(logs.router, prefix="/api/v1")


# ====================================================
# 健康检查接口
# ====================================================

@app.get("/health", tags=["系统"], summary="健康检查")
def health_check():
    """
    用于监控系统探活
    火山引擎、Nginx 等可以定期请求这个接口检查服务是否正常
    """
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


@app.get("/", tags=["系统"], summary="API 根路径")
def root():
    """根路径，跳转提示"""
    return {
        "message": f"欢迎使用 {settings.APP_NAME}",
        "docs": "/docs",
        "version": settings.APP_VERSION
    }
