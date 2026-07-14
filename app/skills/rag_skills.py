"""
RAG 检索相关 Skill（1个）
==========================
Skill 4: search_similar_copies - 从 ChromaDB 向量库检索相似历史文案

RAG = Retrieval-Augmented Generation（检索增强生成）
原理：生成文案时，先从历史文案库里找相似的，
     把它们作为"参考样例"传给模型，让模型学习风格和结构

【为什么 RAG 能提升文案质量？】
没有RAG：模型凭空生成，风格不稳定，可能和用户品牌调性不符
有了RAG：模型参考用户自己的历史爆款，生成的文案风格一致，
         更贴近用户的品牌语气，且往往更容易出爆款

【ChromaDB 的工作原理】
1. 存入文案时：文案文本 -> Embedding API -> 向量（1536维数字数组）-> 存入ChromaDB
2. 检索时：查询文本 -> Embedding API -> 向量 -> 在ChromaDB中找最近邻向量
3. 返回语义最相似的文案，不是关键词匹配，而是"意思相近"

这和普通的 LIKE 查询有本质区别：
   LIKE %AI技术%：只能匹配包含"AI技术"字样的文案
   向量检索：能匹配"人工智能/机器学习/大模型"等语义相近的文案
"""

from sqlalchemy.orm import Session
from app.skills.base import BaseSkill
from app.utils.logger import logger


class SearchSimilarCopiesSkill(BaseSkill):
    """
    Skill 4: 检索相似历史文案
    
    从 ChromaDB 向量库中检索语义相似的历史文案，
    作为文案创作的参考样例
    """

    @property
    def name(self) -> str:
        return "search_similar_copies"

    @property
    def description(self) -> str:
        return (
            "从历史文案库中检索语义相似的优质文案作为创作参考。"
            "当需要参考以往爆款文案风格、结构时调用。"
            "返回最相似的历史文案列表，包含文案内容和质量评分。"
            "有助于保持文案风格一致性，学习爆款结构。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "检索查询文本（如：AI技术相关的小红书爆款文案）"
                },
                "platform": {
                    "type": "string",
                    "description": "限定平台，不传则搜索所有平台",
                    "enum": ["toutiao", "weibo", "wechat", "douyin", "xiaohongshu", "zhihu", "all"]
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量，默认3，最多5",
                    "default": 3
                }
            },
            "required": ["query_text"]
        }

    def execute(self, db: Session, **kwargs) -> dict:
        query_text: str = kwargs.get("query_text", "")
        platform: str = kwargs.get("platform", "all")
        limit: int = min(kwargs.get("limit", 3), 5)

        if not query_text:
            return {"success": False, "error": "查询文本不能为空", "similar_copies": []}

        # 尝试从 ChromaDB 检索
        try:
            similar_copies = self._search_from_chromadb(query_text, platform, limit)
        except Exception as e:
            logger.warning(f"ChromaDB 检索失败，降级到数据库检索: {e}")
            similar_copies = self._search_from_db(db, query_text, platform, limit)

        logger.info(f"相似文案检索: query='{query_text[:30]}...', 找到 {len(similar_copies)} 条")

        if not similar_copies:
            return {
                "success": True,
                "similar_copies": [],
                "message": "暂无相似历史文案，请根据需求和热点自主创作"
            }

        return {
            "success": True,
            "similar_copies": similar_copies,
            "message": f"找到 {len(similar_copies)} 条相似历史文案，可作为风格参考"
        }

    def _search_from_chromadb(self, query_text: str, platform: str, limit: int) -> list[dict]:
        """从 ChromaDB 向量库检索（语义搜索）"""
        import chromadb
        from app.config import settings
        from app.services.embedding_service import EmbeddingService

        client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_PATH)

        # 获取文案 collection
        try:
            collection = client.get_collection("copies")
        except Exception:
            return []  # collection 还没创建，说明还没有历史文案

        # 用 embedding 服务把查询文本向量化
        embedding_service = EmbeddingService()
        query_vector = embedding_service.embed_text_sync(query_text)

        if not query_vector:
            return []

        # 构建过滤条件
        where = {}
        if platform and platform != "all":
            where = {"platform": {"$eq": platform}}

        # 向量检索
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=limit,
            where=where if where else None,
            include=["documents", "metadatas", "distances"]
        )

        copies = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 1.0
                similarity = round(1 - distance, 3)  # 距离转相似度

                copies.append({
                    "content": doc,
                    "title": metadata.get("title", ""),
                    "platform": metadata.get("platform", ""),
                    "review_score": metadata.get("review_score", 0),
                    "similarity": similarity,
                })

        return copies

    def _search_from_db(self, db: Session, query_text: str, platform: str, limit: int) -> list[dict]:
        """
        降级方案：从数据库用关键词搜索（当 ChromaDB 不可用时）
        效果不如向量搜索，但总比没有好
        """
        from app.models.copy import Copy
        from sqlalchemy import desc

        # 提取查询关键词（简单按空格和逗号分割）
        keywords = [w.strip() for w in query_text.replace("，", ",").replace(" ", ",").split(",") if w.strip()]

        query = db.query(Copy).filter(Copy.review_score >= 70)  # 只取高质量文案

        if platform and platform != "all":
            query = query.filter(Copy.platform == platform)

        if keywords:
            from sqlalchemy import or_
            conditions = [Copy.content.like(f"%{kw}%") for kw in keywords[:3]]
            query = query.filter(or_(*conditions))

        copies = query.order_by(desc(Copy.review_score)).limit(limit).all()

        return [
            {
                "content": c.content[:200] + "..." if len(c.content) > 200 else c.content,
                "title": c.title or "",
                "platform": c.platform or "",
                "review_score": c.review_score or 0,
                "similarity": 0.5,  # 关键词匹配，给一个默认相似度
            }
            for c in copies
        ]
