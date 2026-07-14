"""
DeepSeek API 连通性自检
用法：python scripts/test_deepseek.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from app.config import settings
from app.utils.llm_client import get_deepseek_client, format_llm_error


def main():
    print("=" * 50)
    print("DeepSeek API 自检")
    print("=" * 50)
    print(f"BASE_URL: {settings.DEEPSEEK_BASE_URL}")
    print(f"MODEL:    {settings.DEEPSEEK_CHAT_MODEL}")
    key = settings.DEEPSEEK_API_KEY
    print(f"API_KEY:  {(key[:12] + '...') if key else '(未配置)'}")

    if not key:
        print("\n[失败] 请在 .env 中设置 DEEPSEEK_API_KEY")
        sys.exit(1)

    print("\n[1] HTTP 探测 api.deepseek.com ...")
    try:
        r = httpx.get("https://api.deepseek.com", timeout=15.0)
        print(f"    状态码 {r.status_code}（能连上服务器）")
    except Exception as e:
        print(f"    [失败] {type(e).__name__}: {e}")
        print("    -> 网络/DNS/防火墙问题，或需要配置代理 HTTPS_PROXY")
        sys.exit(1)

    print("\n[2] 调用 chat/completions ...")
    try:
        client = get_deepseek_client()
        resp = client.chat.completions.create(
            model=settings.DEEPSEEK_CHAT_MODEL,
            messages=[{"role": "user", "content": "回复 OK 两个字母"}],
            max_tokens=10,
        )
        text = resp.choices[0].message.content
        print(f"    [成功] 模型回复: {text!r}")
        print("\nAPI 正常，若任务仍失败请重启 python run.py 后再试。")
    except Exception as e:
        print(f"    [失败] {format_llm_error(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
