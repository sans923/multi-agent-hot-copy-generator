"""
头条长文 RAG Skill（LangGraph 与自研 Agent 的桥梁）
====================================================

【在整体流程中的位置】

    CopywriterAgent（Function Calling 循环）
        ↓ 模型决定调用工具
    SearchToutiaoReferencesSkill.execute()  ← 本文件
        ↓
    run_rag_query()  ← LangGraph query 图
        ↓
    references 返回给模型，当作「写法参考」写文案

【为什么要有 Skill 这一层？】
    BaseAgent 只认识 SkillRegistry，不直接 import langgraph。
    这是适配器模式：Agent 架构不变，底层 RAG 换成 LangChain+LangGraph。
"""

from sqlalchemy.orm import Session

from app.lang.graph.query_graph import run_rag_query
from app.skills.base import BaseSkill
from app.utils.logger import logger


class SearchToutiaoReferencesSkill(BaseSkill):
    """
    Skill：search_toutiao_references

    注册位置：app/skills/__init__.py → COPYWRITER_AGENT_SKILLS
    调用时机：CopywriterAgent 创作前，学习头条爆款长文的标题与段落结构。
    """

    @property
    def name(self) -> str:
        """Function Calling 里的工具名，模型通过这个名字发起调用。"""
        return "search_toutiao_references"

    @property
    def description(self) -> str:
        """传给大模型的工具说明，影响模型是否、何时调用本 Skill。"""
        return (
            "从今日头条爆款长文库中语义检索写作参考，学习标题结构、段落节奏、论证方式。"
            "创作文案前优先调用，结合热榜话题生成更易传播的内容。"
            "返回相似长文片段列表，含标题与正文摘要。"
        )

    @property
    def parameters_schema(self) -> dict:
        """JSON Schema：定义模型调用本工具时要传哪些参数。"""
        return {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "检索词，如：AI就业 深度分析 爆款标题",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回切块数量，默认3，最大5",
                    "default": 3,
                },
            },
            "required": ["query_text"],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        """
        Skill 执行入口（SkillExecutor 在 Agent 循环里调用）。

        参数（来自模型 tool_call）：
            query_text — 检索主题
            limit      — top_k，最多 5

        流程：
            1. 校验 query_text
            2. run_rag_query() → LangGraph query 图（retrieve → format）
            3. 包装成 {success, references, engine} 返回给 Agent

        db 参数：
            本 Skill 不查 MySQL（检索走 Chroma），但 BaseSkill 接口统一要求 Session。

        在整体流程中：
            这是「在线 RAG」对创作 Agent 的唯一入口。
        """
        query_text = (kwargs.get("query_text") or "").strip()
        limit = min(int(kwargs.get("limit") or 3), 5)

        if not query_text:
            return {"success": False, "error": "query_text 不能为空", "references": []}

        try:
            result = run_rag_query(query_text=query_text, top_k=limit)
            references = result.get("references") or []
        except Exception as e:
            logger.exception(f"头条 RAG 检索失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "references": [],
            }

        logger.info(f"头条 RAG 检索: query={query_text[:40]}, hits={len(references)}")

        if not references:
            return {
                "success": True,
                "references": [],
                "message": "向量库暂无头条长文，请先运行 scripts/import_toutiao_article.py 导入",
            }

        return {
            "success": True,
            "references": references,
            "query": query_text,
            "engine": "langchain_chroma + langgraph",
        }
