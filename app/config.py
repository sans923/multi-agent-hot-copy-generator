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
from pydantic import field_validator, model_validator
from functools import lru_cache
from urllib.parse import quote_plus


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

    # --- 智能体编排引擎选择 ---
    # native   = 自研顺序流水线编排（AgentOrchestrator，默认，行为与历史版本完全一致）
    # langgraph = 基于 LangGraph 的 DeerFlow 2.0 风格编排引擎（后续阶段接入）
    # 双引擎通过此开关切换、运行时隔离；切回 native 即恢复现状
    ORCHESTRATION_ENGINE: str = "native"

    # --- 数据库配置（默认 MySQL；设置 DATABASE_URL 可覆盖）---
    DATABASE_URL: str = ""
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "copygen"
    MYSQL_PASSWORD: str = "copygen123"
    MYSQL_DATABASE: str = "copy_generator"

    # --- JWT 鉴权配置 ---
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 默认 24 小时
    ALGORITHM: str = "HS256"

    # --- DeepSeek API 配置 ---
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_CHAT_MODEL: str = "deepseek-chat"
    DEEPSEEK_EMBEDDING_MODEL: str = "deepseek-embedding"
    DEEPSEEK_TIMEOUT_SECONDS: float = 120.0
    DEEPSEEK_CONNECT_TIMEOUT: float = 15.0
    DEEPSEEK_MAX_RETRIES: int = 2
    DEEPSEEK_MAX_TOKENS: int = 4096

    # --- ChromaDB 配置 ---
    CHROMA_PERSIST_PATH: str = "./data/chroma"

    # --- 头条长文 RAG（LangChain + LangGraph）---
    TOUTIAO_RAG_COLLECTION: str = "toutiao_references"
    RAG_EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    RAG_CHUNK_SIZE: int = 600
    RAG_CHUNK_OVERLAP: int = 80
    RAG_TOP_K: int = 3

    # --- 热榜 API 配置 ---
    JUHE_API_KEY: str = ""
    JUHE_HOTLIST_URL: str = "https://apis.juhe.cn/fapigx/networkhot/query"
    HOTLIST_SYNC_INTERVAL: int = 3600

    # --- 日志配置 ---
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "./logs/app.log"

    @model_validator(mode="after")
    def assemble_database_url(self) -> "Settings":
        """未设置 DATABASE_URL 时，用 MYSQL_* 拼装 MySQL 连接串"""
        if not self.DATABASE_URL.strip():
            user = quote_plus(self.MYSQL_USER)
            password = quote_plus(self.MYSQL_PASSWORD)
            self.DATABASE_URL = (
                f"mysql+pymysql://{user}:{password}@{self.MYSQL_HOST}:"
                f"{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"
            )
        return self

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_long_enough(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY 必须至少 32 个字符，请修改 .env 文件")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
