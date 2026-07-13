"""
LangChain 向量检索（query 图 · retrieve / format 节点的底层实现）
================================================================

【在整体流程中的位置】
    LangGraph query 图 → _retrieve_node / _format_node → 本文件两个函数

【职责】
    retrieve：query 向量 vs 库内向量，相似度 top_k
    format：Document → Agent 可读的 dict 列表
"""

from langchain_core.documents import Document

from app.config import settings
from app.lang.vectorstore import get_toutiao_vectorstore


def retrieve_toutiao_references(query: str, k: int | None = None) -> list[Document]:
    """
    语义检索头条长文切块（query 图 retrieve 节点的核心逻辑）。

    原理（RAG Retrieval）：
        1. query 文本 → Embedding 向量（与入库同一模型）
        2. Chroma similarity_search 找距离最近的 k 个块
        3. filter platform=toutiao，只搜头条库

    参数：
        query — 检索词，通常来自用户主题或 Skill 的 query_text
        k     — 返回条数，默认 settings.RAG_TOP_K

    返回：
        list[Document]，写入 query state 的 documents 字段

    在整体流程中：
        若向量库为空（未 import 过文章），返回 []，format 后 references 也为空。
    """
    top_k = k or settings.RAG_TOP_K
    store = get_toutiao_vectorstore()

    if store._collection.count() == 0:  # noqa: SLF001
        return []

    return store.similarity_search(
        query,
        k=top_k,
        filter={"platform": "toutiao"},
    )


def format_references_for_prompt(docs: list[Document]) -> list[dict]:
    """
    把检索到的 Document 格式化为 Skill / 大模型友好的结构（query 图 format 节点核心逻辑）。

    输出字段说明：
        title, article_id, source_url — 溯源
        content_preview               — 前 400 字，给模型快速浏览
        full_chunk                    — 完整块文本，需要时可深入参考
        chunk_index, keyword          — 调试或展示用

    在整体流程中：
        返回值写入 query state.references → Skill 返回给 CopywriterAgent → 进入 prompt。
    """
    results: list[dict] = []
    for doc in docs:
        meta = doc.metadata or {}
        results.append(
            {
                "title": meta.get("title", ""),
                "article_id": meta.get("article_id", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "source_url": meta.get("source_url", ""),
                "keyword": meta.get("keyword", ""),
                "content_preview": doc.page_content[:400],
                "full_chunk": doc.page_content,
            }
        )
    return results
