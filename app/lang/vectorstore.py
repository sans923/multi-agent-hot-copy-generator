"""
LangChain Chroma 向量库（头条 RAG 的存储层）
============================================

【在整体流程中的位置】
    ingest 图 index 节点 → ingest_documents → 本文件 get_toutiao_vectorstore()
    query 图 retrieve 节点 → retrieve_toutiao_references → 同上

【职责】
    提供 LangChain 封装的 Chroma 实例，持久化到 settings.CHROMA_PERSIST_PATH。

【collection 隔离】
    热榜用 embedding_service 的 hotlist_topics；
    头条长文用 TOUTIAO_RAG_COLLECTION（默认 toutiao_references），互不干扰。
"""

import os

from langchain_chroma import Chroma

from app.config import settings
from app.lang.embeddings import get_embeddings


def get_toutiao_vectorstore() -> Chroma:
    """
    获取头条长文专用的 Chroma VectorStore 实例。

    每次调用返回绑定同一 persist_directory 持久化目录的 Chroma 对象；
    LangChain 会在 add_documents / similarity_search 时自动做 Embedding。

    在整体流程中：
        这是 ingest 图（写）和 query 图（读）共同依赖的存储入口。
    """
    os.makedirs(settings.CHROMA_PERSIST_PATH, exist_ok=True)
    return Chroma(
        collection_name=settings.TOUTIAO_RAG_COLLECTION,
        embedding_function=get_embeddings(),
        persist_directory=settings.CHROMA_PERSIST_PATH,
    )
