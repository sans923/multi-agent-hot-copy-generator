"""
配置管理模块
============
作用：统一读取 .env 文件中的所有配置，让其他模块通过 settings.XXX 访问
原理：pydantic-settings 会自动从 .env 文件读取变量，并做类型转换和校验

使用方法：
    from app.config import settings
    print(settings.APP_NAME)
    print(settings.SECRET_KEY)
"""

from pydantic_settings import BaseSettings
from pydantic import AliasChoices, Field, field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """
    继承 BaseSettings 后，pydantic 会自动：
    1. 读取 .env 文件
    2. 把字符串转换为对应的 Python 类型（如 "true" -> True, "3600" -> 3600）
    3. 如果必填字段缺失，启动时直接报错（快速失败原则）
    """

    # --- 应用基础配置 ---
    APP_NAME: str = "多智能体热点爆款文案生成系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    PORT: int = 8000

    # --- 数据库配置 ---
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # --- JWT 鉴权配置 ---
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 默认 24 小时
    ALGORITHM: str = "HS256"

    # --- 大模型 API 配置 ---
    # 默认按火山方舟 Coding Plan 的 OpenAI 兼容协议配置，API Key 请放到 .env 的 LLM_API_KEY。
    # 兼容旧的 DEEPSEEK_* 环境变量，便于已有部署平滑迁移。
    LLM_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "DEEPSEEK_API_KEY"),
    )
    LLM_BASE_URL: str = Field(
        default="https://ark.cn-beijing.volces.com/api/coding/v3",
        validation_alias=AliasChoices("LLM_BASE_URL", "DEEPSEEK_BASE_URL"),
    )
    LLM_CHAT_MODEL: str = Field(
        default="glm-5.2",
        validation_alias=AliasChoices("LLM_CHAT_MODEL", "DEEPSEEK_CHAT_MODEL"),
    )

    # --- 向量化 API 配置 ---
    # glm-5.2 是聊天/编程模型，不能当作 embedding 模型使用；向量化单独配置。
    EMBEDDING_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices(
            "EMBEDDING_API_KEY",
            "DEEPSEEK_EMBEDDING_API_KEY",
            "LLM_API_KEY",
            "DEEPSEEK_API_KEY",
        ),
    )
    EMBEDDING_BASE_URL: str = Field(
        default="https://api.deepseek.com/v1",
        validation_alias=AliasChoices(
            "EMBEDDING_BASE_URL",
            "DEEPSEEK_EMBEDDING_BASE_URL",
            "DEEPSEEK_BASE_URL",
        ),
    )
    EMBEDDING_MODEL: str = Field(
        default="deepseek-embedding",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "DEEPSEEK_EMBEDDING_MODEL"),
    )

    # --- ChromaDB 配置 ---
    CHROMA_PERSIST_PATH: str = "./data/chroma"

    # --- 热榜 API 配置 ---
    HAN_API_BASE_URL: str = "https://api.vvhan.com/api"
    HOTLIST_SYNC_INTERVAL: int = 3600

    # --- 日志配置 ---
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "./logs/app.log"

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_long_enough(cls, v: str) -> str:
        """
        安全校验：SECRET_KEY 至少 32 个字符
        JWT 签名密钥太短容易被暴力破解
        """
        if len(v) < 32:
            raise ValueError("SECRET_KEY 必须至少 32 个字符，请修改 .env 文件")
        return v

    class Config:
        """
        pydantic-settings 配置类
        env_file: 指定从哪个文件读取环境变量
        case_sensitive: 区分大小写（推荐开启，防止混淆）
        """
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置单例
    
    @lru_cache() 装饰器让这个函数只执行一次：
    - 第一次调用时读取 .env 文件，创建 Settings 对象
    - 之后每次调用直接返回缓存的对象（不重复读文件）
    
    这种模式叫"单例模式"，确保整个应用共享同一份配置
    """
    return Settings()


# 全局配置对象，其他模块直接导入使用
settings = get_settings()
