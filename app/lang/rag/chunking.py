"""
LangChain 文档切块（ingest 图 · chunk 节点的底层实现）
======================================================

【在整体流程中的位置】
    LangGraph ingest 图 → _chunk_node() → 本文件的 article_to_documents()

【职责】
    把一篇头条长文变成多个 LangChain Document，供后续 index 节点写入向量库。

【为什么必须切块？】
    一篇长文几千字，整篇做 embedding 检索不精准；
    切成小块后，用户问「AI就业」可以命中最相关的那几段。
"""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings


def build_text_splitter() -> RecursiveCharacterTextSplitter:
    """
    创建文本分割器（LangChain 组件）。

    参数含义（settings 里可配）：
        chunk_size=600    — 每块大约 600 字符
        chunk_overlap=80  — 相邻块重叠 80 字，避免句子在边界被截断
        separators        — 优先按段落、句号切，尽量保持语义完整

    在整体流程中：
        仅被 article_to_documents 使用，不直接暴露给 Agent。
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "！", "？", " ", ""],
    )


def article_to_documents(
    article_id: str,
    title: str,
    content: str,
    source_url: str,
    keyword: str = "",
    author_name: str = "",
) -> list[Document]:
    """
    把一篇头条长文转为 Document 列表（ingest 图 chunk 节点的核心逻辑）。

    步骤：
        1. 拼接 header（标题、作者、关键词）+ 正文
        2. RecursiveCharacterTextSplitter 切分
        3. 每块包装为 Document(page_content=..., metadata=...)

    metadata 字段用途：
        platform, article_id — Chroma 检索时 filter / 溯源
        chunk_index          — 同一文章内第几块
        source_url, keyword  — 展示给 Agent 或前端

    返回：
        list[Document]，交给 ingest_documents() 写入向量库。

    在整体流程中：
        ingest 图 state.documents 就是本函数的返回值。
    """
    header = f"标题：{title}\n"
    if author_name:
        header += f"作者：{author_name}\n"
    if keyword:
        header += f"关键词：{keyword}\n"
    full_text = header + content

    splitter = build_text_splitter()
    chunks = splitter.split_text(full_text)

    docs: list[Document] = []
    for idx, chunk in enumerate(chunks):
        docs.append(
            Document(
                page_content=chunk,
                metadata={
                    "platform": "toutiao",
                    "article_id": article_id,
                    "title": title,
                    "chunk_index": idx,
                    "source_url": source_url,
                    "keyword": keyword or "",
                    "author_name": author_name or "",
                },
            )
        )
    return docs
