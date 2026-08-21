"""
向量化服务（ChromaDB + sentence-transformers 本地模型）
=======================================================
负责：
1. 把文本转换为向量（本地 sentence-transformers 模型，完全免费）
2. 将热榜话题向量存入 ChromaDB（用于语义搜索）
3. 将用户文档向量存入 ChromaDB（用于 RAG）
4. 提供语义搜索接口（供 Agent Skill 调用）

【向量化是什么？为什么要用它？】
-----------------------------------
传统搜索（关键词匹配）：
  搜索"美妆教程" -> 只能找到包含这三个字的热榜

语义搜索（向量相似度）：
  搜索"美妆教程" -> 能找到"口红试色""护肤分享""化妆技巧"
  因为这些话题的语义相近（向量距离近）

工作原理：
  文本 "美妆教程" -> Embedding模型 -> [0.23, -0.41, 0.87, ...] (384维向量)
  所有热榜话题也被转成向量存在 ChromaDB 里
  搜索时：把查询也转成向量 -> 在 ChromaDB 里找最相近的向量 -> 返回对应文本

【使用模型】
-----------------------------------
paraphrase-multilingual-MiniLM-L12-v2
- 多语言支持（含中文），384维向量
- 首次运行自动下载（~500MB），之后离线使用
- CPU 可运行，无需 GPU

【ChromaDB 核心概念】
-----------------------------------
- Collection（集合）：类比数据库中的"表"，按用途分组存储向量
  本项目使用2个 collection：
  * "hotlist_topics"   - 存热榜话题的向量
  * "user_documents"   - 存用户上传文档的向量

- Document（文档）：被向量化的文本内容
- Embedding（嵌入/向量）：文本对应的高维浮点数组
- Metadata（元数据）：附加的结构化信息（如 platform、rank），用于过滤
- ID：每条记录的唯一标识符
"""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Optional
import chromadb

from app.config import settings
from app.utils.logger import logger


# ====================================================
# 本地 Embedding 模型（sentence-transformers）
# ====================================================

_st_model = None  # 延迟加载，首次调用时初始化

EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384  # 该模型的向量维度


def _schema_vector_space(schema: dict) -> str:
    """Read the distance metric stored by Chroma's newer schema format."""
    vector_config = (
        schema.get("keys", {})
        .get("#embedding", {})
        .get("float_list", {})
        .get("vector_index", {})
        .get("config", {})
    )
    space = vector_config.get("space", "l2")
    return space if space in {"l2", "ip", "cosine"} else "l2"


def _migrate_chroma_collection_configs(database_path: Path) -> int:
    """Repair Chroma 1.x collection configs for the locked Chroma 0.6 runtime."""
    if not database_path.exists():
        return 0

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(collections)")
        }
        required_columns = {"id", "config_json_str", "schema_str"}
        if not required_columns.issubset(columns):
            return 0

        pending_repairs: list[tuple[str, str]] = []
        rows = connection.execute(
            "SELECT id, config_json_str, schema_str FROM collections"
        ).fetchall()

        for collection_id, config_json, schema_json in rows:
            try:
                config = json.loads(config_json or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(config, dict) and config.get("_type"):
                continue

            try:
                schema = json.loads(schema_json or "{}")
            except (TypeError, json.JSONDecodeError):
                schema = {}

            from chromadb.api.configuration import (
                CollectionConfigurationInternal,
                ConfigurationParameter,
                HNSWConfigurationInternal,
            )

            hnsw_config = HNSWConfigurationInternal.from_legacy_params(
                {"hnsw:space": _schema_vector_space(schema)}
            )
            collection_config = CollectionConfigurationInternal(
                [
                    ConfigurationParameter(
                        name="hnsw_configuration",
                        value=hnsw_config,
                    )
                ]
            )
            pending_repairs.append(
                (collection_config.to_json_str(), collection_id)
            )

    if not pending_repairs:
        return 0

    backup_path = database_path.with_suffix(".sqlite3.pre-0.6-config.bak")
    if not backup_path.exists():
        with (
            sqlite3.connect(database_path) as source,
            sqlite3.connect(backup_path) as backup,
        ):
            source.backup(backup)

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            "UPDATE collections SET config_json_str = ? WHERE id = ?",
            pending_repairs,
        )

    logger.warning(
        "已迁移 {} 个 Chroma collection 的旧配置，备份位于 {}",
        len(pending_repairs),
        backup_path,
    )
    return len(pending_repairs)


def _get_st_model():
    """
    获取 sentence-transformers 模型单例（延迟加载）

    首次调用时从 HuggingFace 下载模型（~500MB），之后从本地缓存读取。
    模型缓存路径：~/.cache/huggingface/
    """
    global _st_model
    if _st_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"加载 Embedding 模型: {EMBEDDING_MODEL_NAME}（首次运行需下载）")
            _st_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("Embedding 模型加载完成")
        except ImportError:
            raise RuntimeError(
                "sentence-transformers 未安装，请运行: pip install sentence-transformers"
            )
    return _st_model


def _create_chroma_client() -> chromadb.PersistentClient:
    """
    创建 ChromaDB 持久化客户端

    PersistentClient：向量数据持久化到磁盘（重启后数据不丢失）
    路径：settings.CHROMA_PERSIST_PATH（如 ./data/chroma）
    """
    os.makedirs(settings.CHROMA_PERSIST_PATH, exist_ok=True)
    _migrate_chroma_collection_configs(
        Path(settings.CHROMA_PERSIST_PATH) / "chroma.sqlite3"
    )
    return chromadb.PersistentClient(path=settings.CHROMA_PERSIST_PATH)


_chroma_client: Optional[chromadb.PersistentClient] = None


def get_chroma_client() -> chromadb.PersistentClient:
    """获取 ChromaDB 客户端单例"""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = _create_chroma_client()
    return _chroma_client


# ====================================================
# Collection 名称常量（避免拼写错误）
# ====================================================
HOTLIST_COLLECTION = "hotlist_topics"    # 热榜话题
DOCUMENTS_COLLECTION = "user_documents"  # 用户文档


# ====================================================
# 核心：文本向量化
# ====================================================

def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    批量将文本转换为向量（使用本地 sentence-transformers 模型）

    参数：
        texts: 文本列表

    返回：
        list[list[float]]：每个文本对应的 384 维向量
    """
    if not texts:
        return []

    model = _get_st_model()

    try:
        # encode() 返回 numpy array，转为 Python list 存入 ChromaDB
        embeddings = model.encode(texts, show_progress_bar=False)
        vectors = embeddings.tolist()
        logger.debug(f"向量化完成: {len(texts)} 条文本，向量维度: {len(vectors[0])}")
        return vectors

    except Exception as e:
        logger.error(f"Embedding 模型调用失败: {e}")
        raise


def embed_single(text: str) -> list[float]:
    """向量化单条文本（便捷方法）"""
    results = embed_texts([text])
    return results[0] if results else []


# ====================================================
# 热榜话题向量化存储
# ====================================================

def upsert_hotlist_to_chroma(hotlist_items: list[dict]) -> int:
    """
    将热榜话题向量化后存入 ChromaDB

    参数：
        hotlist_items: 热榜条目列表，每条包含：
            - id: hotlist_sync 表的主键（用作 ChromaDB ID）
            - title: 话题标题（被向量化的主要内容）
            - description: 话题描述（拼接到向量化文本中）
            - source_platform: 来源平台
            - rank: 排名
            - hot_value: 热度值

    返回：成功向量化的条数

    ChromaDB upsert 说明：
    - 如果 ID 已存在 -> 更新（防止重复插入）
    - 如果 ID 不存在 -> 插入
    """
    if not hotlist_items:
        return 0

    chroma = get_chroma_client()
    collection = chroma.get_or_create_collection(
        name=HOTLIST_COLLECTION,
        # 指定距离度量方式：cosine（余弦相似度）比 l2（欧氏距离）更适合语义搜索
        metadata={"hnsw:space": "cosine"}
    )

    # 准备批量处理的数据
    ids = []
    documents = []  # 被向量化的文本（标题+描述拼接）
    metadatas = []  # 不被向量化，但可用于过滤的元数据

    for item in hotlist_items:
        item_id = str(item["id"])

        # 拼接标题和描述，提供更丰富的语义信息
        doc_text = item["title"]
        if item.get("description"):
            doc_text = f"{item['title']}。{item['description']}"

        ids.append(item_id)
        documents.append(doc_text)
        metadatas.append({
            "platform": item.get("source_platform", "unknown"),
            "rank": item.get("rank", 0),
            "hot_value": str(item.get("hot_value", "")),
            "title": item["title"],  # 冗余存储，方便检索时直接读取
        })

    # 批量向量化（一次 API 调用处理所有文本，节省费用）
    try:
        embeddings = embed_texts(documents)
    except Exception as e:
        logger.error(f"热榜向量化失败: {e}")
        return 0

    # 存入 ChromaDB
    # upsert = insert + update（有则更新，无则插入）
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    logger.info(f"热榜话题写入 ChromaDB: {len(ids)} 条")
    return len(ids)


# ====================================================
# 用户文档向量化存储
# ====================================================

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    将长文本切分成小块（Chunking）

    【为什么要切分？】
    - Embedding API 对单次输入有长度限制
    - 长文本向量化后信息损失大（一个向量不足以代表整篇文章）
    - 切成小块后，每块向量更精准，检索更准确

    【切分策略】
    - chunk_size=500：每块约500个字符
    - overlap=50：相邻块有50字符重叠（防止关键信息被切断）

    示例：
    文本: "ABCDEFGHIJ"（假设每字符=50字）
    块1: "ABCDE" (0-500)
    块2: "DEFGH" (450-950，前50字与块1重叠)
    块3: "GHIJ"  (900-end)
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # 尽量在句号/换行处切断，而不是硬切
        if end < len(text):
            # 在最后50字符内找句末标点
            last_period = max(
                chunk.rfind("。"),
                chunk.rfind("\n"),
                chunk.rfind("！"),
                chunk.rfind("？"),
            )
            if last_period > chunk_size // 2:  # 找到了合适的切断点
                end = start + last_period + 1
                chunk = text[start:end]

        chunks.append(chunk.strip())
        start = end - overlap  # 下一块从 overlap 处开始，制造重叠

    return [c for c in chunks if c]  # 过滤空块


def upsert_document_to_chroma(
    document_id: int,
    user_id: int,
    content: str,
    filename: str,
) -> int:
    """
    将用户文档向量化后存入 ChromaDB

    参数：
        document_id: documents 表的主键
        user_id: 所属用户ID（用于隔离不同用户的文档）
        content: 文档纯文本内容
        filename: 原始文件名（存在元数据里）

    返回：成功向量化的块数

    Collection 设计：
    - 所有用户文档存在同一个 collection（方便管理）
    - 通过 metadata.user_id 过滤（每个用户只能搜到自己的文档）
    - ID 格式：f"doc_{document_id}_chunk_{chunk_idx}"
    """
    if not content.strip():
        logger.warning(f"文档 {document_id} 内容为空，跳过向量化")
        return 0

    chroma = get_chroma_client()
    collection = chroma.get_or_create_collection(
        name=DOCUMENTS_COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )

    # 切分文本
    chunks = chunk_text(content, chunk_size=500, overlap=50)
    logger.info(f"文档 {document_id} 切分为 {len(chunks)} 块")

    ids = []
    documents = []
    metadatas = []

    for idx, chunk in enumerate(chunks):
        chunk_id = f"doc_{document_id}_chunk_{idx}"
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "document_id": document_id,
            "user_id": user_id,
            "filename": filename,
            "chunk_index": idx,
            "total_chunks": len(chunks),
        })

    # 批量向量化并存储
    try:
        embeddings = embed_texts(documents)
    except Exception as e:
        logger.error(f"文档 {document_id} 向量化失败: {e}")
        return 0

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    logger.info(f"文档 {document_id} 向量化完成，{len(chunks)} 块已存入 ChromaDB")
    return len(chunks)


# ====================================================
# 语义搜索（供 Agent Skill 调用）
# ====================================================

def search_hotlist(
    query: str,
    n_results: int = 5,
    platform_filter: Optional[str] = None,
) -> list[dict]:
    """
    在热榜话题中进行语义搜索

    参数：
        query: 搜索查询文本（如用户需求描述）
        n_results: 返回最相似的前N条
        platform_filter: 限定平台（None=全平台搜索）

    返回：
        list[dict]，每条包含：
        - title: 话题标题
        - platform: 来源平台
        - rank: 排名
        - distance: 相似度距离（越小越相似，0=完全一样）

    这个函数是 Phase 3 中 "search_hotlist" Skill 的核心实现
    """
    chroma = get_chroma_client()

    try:
        collection = chroma.get_collection(name=HOTLIST_COLLECTION)
    except Exception:
        logger.warning("热榜 ChromaDB collection 不存在，可能还未同步过热榜数据")
        return []

    # 把查询文本向量化
    query_embedding = embed_single(query)
    if not query_embedding:
        return []

    # 构建过滤条件
    where = None
    if platform_filter:
        where = {"platform": {"$eq": platform_filter}}

    # 向量相似度搜索
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),  # 不超过总数
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    # 格式化返回结果
    formatted = []
    if results["documents"] and results["documents"][0]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            formatted.append({
                "title": meta.get("title", doc[:50]),
                "platform": meta.get("platform", "unknown"),
                "rank": meta.get("rank", 0),
                "hot_value": meta.get("hot_value", ""),
                "distance": round(dist, 4),
                "similarity": round(1 - dist, 4),  # 转为相似度（越大越相似）
            })

    return formatted


def search_documents(
    query: str,
    user_id: int,
    n_results: int = 3,
) -> list[dict]:
    """
    在用户文档中进行语义搜索（RAG 检索）

    参数：
        query: 搜索查询
        user_id: 只搜索该用户的文档（数据隔离）
        n_results: 返回最相似的前N个文档块

    这个函数是 Phase 3 中 "search_documents" Skill 的核心实现
    """
    chroma = get_chroma_client()

    try:
        collection = chroma.get_collection(name=DOCUMENTS_COLLECTION)
    except Exception:
        logger.warning("文档 ChromaDB collection 不存在")
        return []

    query_embedding = embed_single(query)
    if not query_embedding:
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        where={"user_id": {"$eq": user_id}},  # 只搜该用户的文档
        include=["documents", "metadatas", "distances"],
    )

    formatted = []
    if results["documents"] and results["documents"][0]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            formatted.append({
                "content": doc,
                "filename": meta.get("filename", ""),
                "document_id": meta.get("document_id"),
                "chunk_index": meta.get("chunk_index", 0),
                "distance": round(dist, 4),
                "similarity": round(1 - dist, 4),
            })

    return formatted


# ====================================================
# 清理过期向量（定期维护用）
# ====================================================

def delete_hotlist_vectors(hotlist_ids: list[int]) -> None:
    """
    从 ChromaDB 删除指定热榜话题的向量

    当热榜数据过期超过7天时，可以调用此函数清理 ChromaDB 空间
    （数据库中的记录保留用于历史分析）
    """
    if not hotlist_ids:
        return

    chroma = get_chroma_client()
    try:
        collection = chroma.get_collection(name=HOTLIST_COLLECTION)
        ids_to_delete = [str(hid) for hid in hotlist_ids]
        collection.delete(ids=ids_to_delete)
        logger.info(f"已从 ChromaDB 删除 {len(ids_to_delete)} 条过期热榜向量")
    except Exception as e:
        logger.error(f"删除 ChromaDB 向量失败: {e}")
