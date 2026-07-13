"""
LangChain 向量入库（ingest 图 · index 节点的底层实现）
======================================================

【在整体流程中的位置】
    LangGraph ingest 图 → _index_node() → 本文件的 ingest_documents()

【职责】
    把 chunk 节点产出的 Document 列表写入 Chroma，并完成 Embedding。
"""

from langchain_core.documents import Document

from app.lang.vectorstore import get_toutiao_vectorstore
from app.utils.logger import logger


def delete_article_chunks(article_id: str) -> None:
    """
    删除某篇文章在 Chroma 中的全部旧切块。

    为什么需要：
        同一 article_id 重新 import 时，若不清旧块会重复检索、浪费空间。

    在整体流程中：
        ingest_documents 写入前自动调用；不经过 LangGraph 节点，是 index 的内部步骤。
    """
    store = get_toutiao_vectorstore()
    collection = store._collection  # noqa: SLF001 — LangChain Chroma 内部 collection API
    try:
        existing = collection.get(where={"article_id": article_id})
        ids = existing.get("ids") or []
        if ids:
            collection.delete(ids=ids)
            logger.info(f"已删除头条旧向量块: article_id={article_id}, count={len(ids)}")
    except Exception as e:
        logger.warning(f"删除旧向量块失败 article_id={article_id}: {e}")


def ingest_documents(documents: list[Document]) -> int:
    """
    将 Document 列表写入 Chroma 向量库（ingest 图 index 节点的核心逻辑）。

    步骤：
        1. 若 documents 为空，返回 0
        2. 按 article_id 删除旧块（幂等：同一文章可重复 import）
        3. 为每块生成唯一 id：toutiao_{article_id}_{chunk_index}
        4. store.add_documents — LangChain 自动调 Embedding 再写入 Chroma

    返回：
        成功写入的块数量 → 写入 ingest state 的 chunk_count

    在整体流程中：
        import 脚本用 chunk_count 更新 MySQL toutiao_reference.embedding_status。
    """
    if not documents:
        return 0

    article_id = documents[0].metadata.get("article_id", "")
    if article_id:
        delete_article_chunks(article_id)

    store = get_toutiao_vectorstore()
    ids = [
        f"toutiao_{article_id}_{doc.metadata.get('chunk_index', i)}"
        for i, doc in enumerate(documents)
    ]
    store.add_documents(documents=documents, ids=ids)
    logger.info(f"头条 RAG 入库: article_id={article_id}, chunks={len(documents)}")
    return len(documents)
