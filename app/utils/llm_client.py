"""
DeepSeek / OpenAI 兼容客户端（统一超时、重试）
"""

from typing import Optional
import httpx
from openai import OpenAI

from app.config import settings
from app.utils.logger import logger

_client: Optional[OpenAI] = None


def get_deepseek_client() -> OpenAI:
    """获取 DeepSeek 客户端单例（带超时与自动重试）"""
    global _client
    if _client is None:
        if not settings.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY 未配置，请在 .env 中填写")

        timeout = httpx.Timeout(
            settings.DEEPSEEK_TIMEOUT_SECONDS,
            connect=settings.DEEPSEEK_CONNECT_TIMEOUT,
        )
        _client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL.rstrip("/"),
            timeout=timeout,
            max_retries=settings.DEEPSEEK_MAX_RETRIES,
        )
        logger.debug(
            f"DeepSeek 客户端已初始化: base_url={settings.DEEPSEEK_BASE_URL}, "
            f"timeout={settings.DEEPSEEK_TIMEOUT_SECONDS}s, "
            f"retries={settings.DEEPSEEK_MAX_RETRIES}"
        )
    return _client


def reset_deepseek_client() -> None:
    """测试或热重载配置时重置客户端"""
    global _client
    _client = None


def format_llm_error(exc: Exception) -> str:
    """把底层连接错误转成可读提示"""
    msg = str(exc) or repr(exc)
    name = type(exc).__name__
    hints: list[str] = []

    if "Connection" in msg or "Connect" in name or "Timeout" in name:
        hints.append("请检查本机能否访问 https://api.deepseek.com")
        hints.append("若使用代理，在系统或终端设置 HTTPS_PROXY 后重启后端")
        hints.append("确认 .env 中 DEEPSEEK_API_KEY 有效且有余额")
    if "401" in msg or "authentication" in msg.lower():
        hints.append("API Key 无效，请到 platform.deepseek.com 重新复制 Key")

    detail = f"{name}: {msg}"
    if hints:
        detail += "。建议：" + "；".join(hints)
    return detail
