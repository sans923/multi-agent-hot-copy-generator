"""
LangChain Embedding 封装（入库与检索共用的向量化模型）
======================================================

【在整体流程中的位置】
    入库：ingest_documents → add_documents → 内部调 get_embeddings()
    检索：similarity_search → 内部调 get_embeddings()

【职责】
    把文本变成 384 维浮点向量；入库和检索必须用同一套模型，否则相似度无意义。

【与 app/services/embedding_service.py 的关系】
    热榜仍用 embedding_service；头条 RAG 走 LangChain HuggingFaceEmbeddings。
    模型名相同：paraphrase-multilingual-MiniLM-L12-v2
"""

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings
from app.services.embedding_service import (
    EMBEDDING_MODEL_REPO_ID,
    _huggingface_offline_mode,
)


def _resolve_embedding_model() -> tuple[str, bool]:
    """Return a local snapshot when available, otherwise allow first download."""
    from huggingface_hub import snapshot_download

    try:
        with _huggingface_offline_mode():
            return (
                snapshot_download(
                    repo_id=EMBEDDING_MODEL_REPO_ID,
                    local_files_only=True,
                ),
                True,
            )
    except OSError:
        return settings.RAG_EMBEDDING_MODEL, False


@lru_cache()
def get_embeddings() -> HuggingFaceEmbeddings:
    """
    获取 Embedding 模型单例（进程内只加载一次，约 500MB）。

    normalize_embeddings=True：
        向量归一化后，余弦相似度等价于点积，Chroma 检索更稳定。

    在整体流程中：
        被 get_toutiao_vectorstore() 注入到 Chroma，所有头条 RAG 向量操作都经此模型。
    """
    model_name, local_files_only = _resolve_embedding_model()
    model_kwargs = {"device": "cpu"}
    if local_files_only:
        model_kwargs["local_files_only"] = True

    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs=model_kwargs,
        encode_kwargs={"normalize_embeddings": True},
    )
