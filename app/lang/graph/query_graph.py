"""
LangGraph：头条长文【检索图】
=============================

【在整体 RAG 流程中的位置】
    在线阶段，创作文案时：

        CopywriterAgent → Skill(search_toutiao_references)
            → 【本图：检索 + 格式化】 → references 给大模型

【图结构】
        START
          ↓
        retrieve  （向量相似度搜索 Chroma）
          ↓
        format    （Document → 给 Agent 用的 dict 列表）
          ↓
        END

【对外入口】
    run_rag_query() — Skill / scripts/query_toutiao_rag.py 调用

【与 ingest 图的关系】
    ingest 图负责「写入」；query 图负责「读出」。
    两者共用同一 Chroma collection（toutiao_references），通过 Embedding 语义匹配。
"""

from langgraph.graph import END, StateGraph

from app.config import settings
from app.lang.graph.state import QueryState
from app.lang.rag.retriever import format_references_for_prompt, retrieve_toutiao_references


def _retrieve_node(state: QueryState) -> dict:
    """
    【检索图 · 节点 1】向量检索（retrieve）

    职责：
        根据 query_text 在 Chroma 里做 similarity_search，取 top_k 条最相似切块。

    输入（从 state 读取）：
        query_text — 用户主题或 Skill 传入的检索词
        top_k      — 返回条数，缺省用 settings.RAG_TOP_K

    输出（合并回 state）：
        documents: list[Document]

    实际干活的是：
        app.lang.rag.retriever.retrieve_toutiao_references()
        内部用 LangChain Chroma.similarity_search + filter platform=toutiao

    在整体流程中：
        相当于 RAG 的「Retrieval」阶段；还没有调用 LLM 生成，只是找资料。
    """
    query = state.get("query_text", "")
    top_k = state.get("top_k") or settings.RAG_TOP_K
    docs = retrieve_toutiao_references(query, k=top_k)
    return {"documents": docs}


def _format_node(state: QueryState) -> dict:
    """
    【检索图 · 节点 2】格式化（format）

    职责：
        把 LangChain Document 转成 Agent / JSON 友好的 dict 结构。

    输入（从 state 读取）：
        documents — retrieve 节点的检索结果（可能为空列表）

    输出（合并回 state）：
        references: list[dict]
        每项含 title, article_id, content_preview, source_url 等

    为什么单独一个节点？
        1. 检索与展示解耦：以后 retrieve 可换 Milvus，format 规则不变
        2. 符合 LangGraph「一个节点一件事」；面试好讲清数据流

    在整体流程中：
        format 之后的 references 会进入 Skill 返回值 → 大模型 prompt 当 few-shot 参考。
    """
    docs = state.get("documents") or []
    return {"references": format_references_for_prompt(docs)}


def build_query_graph():
    """
    构建并编译【检索 StateGraph】（工厂函数）。

    与 build_ingest_graph 结构相同，只是 state 类型和节点不同：
        retrieve → format → END

    返回值：
        编译后的图，供 run_rag_query 单例 invoke。
    """
    graph = StateGraph(QueryState)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("format", _format_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "format")
    graph.add_edge("format", END)
    return graph.compile()


# 全局单例：检索图只 compile 一次
_query_graph = None


def run_rag_query(query_text: str, top_k: int | None = None) -> dict:
    """
    【检索图 · 对外唯一入口】执行一次完整的「向量检索 → 格式化」。

    参数：
        query_text — 检索词，如「AI就业 爆款标题」
        top_k      — 返回几条参考片段，默认 settings.RAG_TOP_K

    返回：
        invoke 结束后的完整 state，业务侧主要用：
        - references: list[dict]  ← Skill 取这个字段
        - documents: 原始 Document（调试时可看）

    调用链示例：
        SearchToutiaoReferencesSkill.execute()
            → run_rag_query(query_text, top_k=limit)
                → _query_graph.invoke(initial)
                    → _retrieve_node → _format_node

    在整体流程中：
        这是「从 RAG 向量库拿写法参考」的唯一 LangGraph 入口。
    """
    global _query_graph
    if _query_graph is None:
        _query_graph = build_query_graph()

    initial: QueryState = {
        "query_text": query_text,
        "top_k": top_k or settings.RAG_TOP_K,
    }
    return _query_graph.invoke(initial)
