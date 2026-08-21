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


class MemoryIndexUnavailable(RuntimeError):
    """向量索引不可用，应进入关系数据库安全降级。"""


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
        similarity_threshold = max(0.0, min(float(kwargs.get("similarity_threshold", 0.35)), 1.0))
        max_context_chars = max(100, min(int(kwargs.get("max_context_chars", 1800)), 10_000))
        trusted_task_id = kwargs.get("_task_id") or kwargs.get("task_id")

        if not query_text:
            return {"success": False, "error": "查询文本不能为空", "similar_copies": []}

        from app.models.task import Task

        task = db.query(Task).filter(Task.id == trusted_task_id).first()
        if task is None:
            return {
                "success": False,
                "error": "缺少有效的任务上下文，无法安全检索历史文案",
                "similar_copies": [],
            }
        user_id = task.user_id

        lexical_results = self._search_from_db(
            db, query_text, platform, limit * 2, user_id=user_id
        )
        retrieval_source = "hybrid"
        try:
            vector_results = self._search_from_chromadb(
                query_text, platform, limit * 2, user_id=user_id
            )
        except Exception as e:
            logger.warning(f"ChromaDB 检索失败，降级到数据库检索: {e}")
            vector_results = []
            retrieval_source = "database_fallback"

        self._attach_feedback_scores(
            db,
            user_id=user_id,
            items=[*vector_results, *lexical_results],
        )

        similar_copies = self._merge_and_budget_results(
            vector_results,
            lexical_results,
            limit=limit,
            similarity_threshold=similarity_threshold,
            max_context_chars=max_context_chars,
        )

        logger.info(f"相似文案检索: query='{query_text[:30]}...', 找到 {len(similar_copies)} 条")

        if not similar_copies:
            return {
                "success": True,
                "similar_copies": [],
                "retrieval_source": retrieval_source,
                "message": "暂无相似历史文案，请根据需求和热点自主创作"
            }

        return {
            "success": True,
            "similar_copies": similar_copies,
            "retrieval_source": retrieval_source,
            "message": f"找到 {len(similar_copies)} 条相似历史文案，可作为风格参考"
        }

    def _search_from_chromadb(
        self,
        query_text: str,
        platform: str,
        limit: int,
        *,
        user_id: int,
    ) -> list[dict]:
        """从 ChromaDB 向量库检索（语义搜索）"""
        import chromadb
        from app.config import settings
        from app.services.embedding_service import embed_single

        client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_PATH)

        # 获取文案 collection
        try:
            collection = client.get_collection("copies")
        except Exception as exc:
            raise MemoryIndexUnavailable("历史文案向量集合不存在") from exc

        # 用 embedding 服务把查询文本向量化
        query_vector = embed_single(query_text)

        if not query_vector:
            return []

        # 构建过滤条件
        conditions = [{"user_id": {"$eq": user_id}}]
        if platform and platform != "all":
            conditions.append({"platform": {"$eq": platform}})
        where = conditions[0] if len(conditions) == 1 else {"$and": conditions}

        # 向量检索
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=limit,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        copies = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 1.0
                similarity = round(1 - distance, 3)  # 距离转相似度

                copies.append({
                    "copy_id": metadata.get("copy_id"),
                    "content": doc,
                    "title": metadata.get("title", ""),
                    "platform": metadata.get("platform", ""),
                    "review_score": metadata.get("review_score", 0),
                    "similarity": similarity,
                })

        return copies

    def _search_from_db(
        self,
        db: Session,
        query_text: str,
        platform: str,
        limit: int,
        *,
        user_id: int,
    ) -> list[dict]:
        """
        降级方案：从数据库用关键词搜索（当 ChromaDB 不可用时）
        效果不如向量搜索，但总比没有好
        """
        from app.models.copy import Copy
        from app.models.task import Task
        from sqlalchemy import desc

        # 提取查询关键词（简单按空格和逗号分割）
        keywords = [w.strip() for w in query_text.replace("，", ",").replace(" ", ",").split(",") if w.strip()]

        query = (
            db.query(Copy)
            .join(Task, Task.id == Copy.task_id)
            .filter(Task.user_id == user_id, Copy.review_score >= 70)
        )

        if platform and platform != "all":
            query = query.filter(Copy.platform == platform)

        if keywords:
            from sqlalchemy import or_
            conditions = [Copy.content.like(f"%{kw}%") for kw in keywords[:3]]
            query = query.filter(or_(*conditions))

        copies = query.order_by(desc(Copy.review_score)).limit(limit).all()

        return [
            {
                "copy_id": c.id,
                "content": c.content[:200] + "..." if len(c.content) > 200 else c.content,
                "title": c.title or "",
                "platform": c.platform or "",
                "review_score": c.review_score or 0,
                "similarity": 0.5,  # 关键词匹配，给一个默认相似度
            }
            for c in copies
        ]

    @staticmethod
    def _merge_and_budget_results(
        vector_results: list[dict],
        lexical_results: list[dict],
        *,
        limit: int,
        similarity_threshold: float,
        max_context_chars: int,
    ) -> list[dict]:
        merged: dict[str, dict] = {}
        for item in vector_results:
            similarity = float(item.get("similarity", 0) or 0)
            if similarity < similarity_threshold:
                continue
            key = str(item.get("copy_id") or f"text:{item.get('content', '')}")
            merged[key] = dict(item)
        for item in lexical_results:
            key = str(item.get("copy_id") or f"text:{item.get('content', '')}")
            if key not in merged:
                merged[key] = dict(item)
        ranked = sorted(
            merged.values(),
            key=lambda item: (
                0.40 * float(item.get("similarity", 0.5) or 0)
                + 0.25 * min(float(item.get("review_score", 0) or 0) / 100, 1.0)
                + 0.35 * float(item.get("feedback_score", 0.5) or 0)
            ),
            reverse=True,
        )
        output: list[dict] = []
        used = 0
        for item in ranked[:limit]:
            remaining = max_context_chars - used
            if remaining <= 0:
                break
            compact = dict(item)
            compact["content"] = str(compact.get("content", ""))[:remaining]
            if not compact["content"]:
                continue
            used += len(compact["content"])
            output.append(compact)
        return output

    @staticmethod
    def _attach_feedback_scores(
        db: Session,
        *,
        user_id: int,
        items: list[dict],
    ) -> None:
        from sqlalchemy import func
        from app.models.memory import MemoryFeedback

        copy_ids = sorted({
            int(item["copy_id"])
            for item in items
            if item.get("copy_id") is not None
        })
        scores: dict[int, float] = {}
        if copy_ids:
            rows = (
                db.query(
                    MemoryFeedback.copy_id,
                    func.avg(MemoryFeedback.rating),
                )
                .filter(
                    MemoryFeedback.user_id == user_id,
                    MemoryFeedback.copy_id.in_(copy_ids),
                )
                .group_by(MemoryFeedback.copy_id)
                .all()
            )
            scores = {
                int(copy_id): (float(average or 0) + 1.0) / 2.0
                for copy_id, average in rows
            }
        for item in items:
            copy_id = item.get("copy_id")
            item["feedback_score"] = scores.get(int(copy_id), 0.5) if copy_id else 0.5
