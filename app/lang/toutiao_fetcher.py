"""
头条文章抓取（LangGraph 流水线【之前】的数据源）
================================================

【在整体流程中的位置】
    import 脚本第 1 步 → fetch_toutiao_article()
    之后才 MySQL → run_ingest()（LangGraph）

【不属于 LangGraph】
    普通 httpx + 正则/JSON 解析；LangGraph 从「已有 title/content」开始编排。

【输出】
    结构化 dict，供 MySQL 与 run_ingest() 使用。
"""

from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import unquote

import httpx

from app.utils.logger import logger

# 从 URL 提取文章 ID，例如 .../article/7434425099895210546/
_ARTICLE_ID_RE = re.compile(r"/article/(\d+)")
# 头条 SSR 页面常把 JSON 放在 id=RENDER_DATA 的 script 里（URL 编码）
_RENDER_DATA_RE = re.compile(
    r'<script[^>]+id=["\']RENDER_DATA["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def extract_article_id(url: str) -> str:
    """
    从头条文章 URL 解析 article_id。

    在整体流程中：
        作为 toutiao_reference.article_id 和 Chroma metadata 的主键。
    """
    m = _ARTICLE_ID_RE.search(url)
    if not m:
        raise ValueError(f"不是有效的头条文章链接: {url}")
    return m.group(1)


def _strip_html(text: str) -> str:
    """把 HTML 片段转成纯文本（内部工具，解析正文时用）。"""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def _find_title_content(obj, title: str = "", content: str = "") -> tuple[str, str]:
    """
    递归遍历 JSON，找 title / content 字段（内部工具）。

    头条 RENDER_DATA 结构较深，不固定路径，所以用递归而不是写死 key 路径。
    """
    if isinstance(obj, dict):
        if not title:
            for key in ("title", "article_title", "name"):
                val = obj.get(key)
                if isinstance(val, str) and len(val.strip()) > 3:
                    title = val.strip()
                    break
        if not content or len(content) < 50:
            for key in ("content", "article_content", "text", "abstract"):
                val = obj.get(key)
                if isinstance(val, str) and len(val.strip()) > len(content):
                    content = _strip_html(val.strip())
        for val in obj.values():
            title, content = _find_title_content(val, title, content)
    elif isinstance(obj, list):
        for item in obj:
            title, content = _find_title_content(item, title, content)
    return title, content


def _parse_render_data(html: str) -> tuple[str, str]:
    """
    从页面 HTML 中解析 RENDER_DATA script 里的标题和正文（内部工具）。
    """
    m = _RENDER_DATA_RE.search(html)
    if not m:
        return "", ""
    raw = unquote(m.group(1).strip())
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "", ""
    return _find_title_content(data)


def fetch_toutiao_article(url: str, timeout: float = 30.0) -> dict:
    """
    【抓取入口】请求头条文章页并提取 title + content。

    流程：
        1. extract_article_id
        2. httpx GET 页面
        3. _parse_render_data 解析正文
        4. 失败则抛 RuntimeError（提示 Cookie/反爬）

    返回字段（→ MySQL + run_ingest 参数）：
        article_id, title, content, source_url, author_name

    在整体流程中：
        scripts/import_toutiao_article.py 第 [1/3] 步调用本函数。
    """
    article_id = extract_article_id(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.toutiao.com/",
    }

    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text

    title, content = _parse_render_data(html)

    if not content:
        title_m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        if title_m and not title:
            title = title_m.group(1).split("_")[0].strip()

    if not content or len(content) < 30:
        raise RuntimeError(
            "未能解析头条正文。可能原因：页面结构变更、需要登录 Cookie、或触发了反爬。"
            "可改用 NewsCrawler 抓取后手动 import，或在 fetcher 中加 Cookie 请求头。"
        )

    if not title:
        title = f"头条文章-{article_id}"

    author_name = ""
    author_m = re.search(r'"media_name"\s*:\s*"([^"]+)"', html)
    if author_m:
        author_name = author_m.group(1)

    logger.info(f"头条抓取成功: article_id={article_id}, title={title[:40]}..., len={len(content)}")

    return {
        "article_id": article_id,
        "title": title[:500],
        "content": content,
        "source_url": url,
        "author_name": author_name,
    }
