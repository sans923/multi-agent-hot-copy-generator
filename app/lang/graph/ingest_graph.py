"""
LangGraph：头条长文【入库图】
=============================

【在整体 RAG 流程中的位置】
    离线阶段，在 MySQL 已保存原文之后执行：

        抓取正文 → MySQL → 【本图：切块 + 向量化入库】 → Chroma

【图结构】
        START
          ↓
        chunk   （长文 → 多个 Document 块）
          ↓
        index   （Document 块 → 写入 Chroma 向量库）
          ↓
        END

【对外入口】
    run_ingest() — scripts/import_toutiao_article.py 调用

【设计说明】
    当前只有「固定边」，没有条件分支；适合确定性流水线。
    以后可在 chunk 与 index 之间插入：LLM 摘要、质量过滤、去重等节点。
"""

from langgraph.graph import END, StateGraph

from app.lang.graph.state import IngestState
from app.lang.rag.chunking import article_to_documents
from app.lang.rag.ingest import ingest_documents


def _chunk_node(state: IngestState) -> dict:
    """
    【入库图 · 节点 1】切块（chunk）

    职责：
        把 state 里的一篇长文（title + content）切成多个 LangChain Document。

    输入（从 state 读取）：
        article_id, title, content, source_url, keyword, author_name

    输出（合并回 state）：
        documents: list[Document]

    实际干活的是：
        app.lang.rag.chunking.article_to_documents()
        （LangChain RecursiveCharacterTextSplitter，不是 LangGraph）

    在整体流程中：
        相当于 RAG 的「Indexing 前半段：Document Loading + Splitting」
    """
    docs = article_to_documents(
        article_id=state["article_id"],
        title=state["title"],
        content=state["content"],
        source_url=state["source_url"],
        keyword=state.get("keyword", ""),
        author_name=state.get("author_name", ""),
    )
    return {"documents": docs}


def _index_node(state: IngestState) -> dict:
    """
    【入库图 · 节点 2】入库（index）

    职责：
        把 chunk 节点产出的 documents 写入 Chroma 向量库（含 Embedding）。

    输入（从 state 读取）：
        documents（若为空则 ingest 0 条）

    输出（合并回 state）：
        chunk_count: int

    实际干活的是：
        app.lang.rag.ingest.ingest_documents()
        内部会先 delete_article_chunks 再 add_documents，避免重复入库。

    在整体流程中：
        相当于 RAG 的「Indexing 后半段：Embedding + Vector Store Upsert」
    """
    count = ingest_documents(state.get("documents") or [])
    return {"chunk_count": count}


def build_ingest_graph():
    """
    构建并编译【入库 StateGraph】（工厂函数）。

    步骤说明：
        1. StateGraph(IngestState)  — 指定本图使用的 state 类型
        2. add_node                 — 注册节点函数（节点）
        3. set_entry_point          — 入口节点（从哪开始跑）
        4. add_edge                 — 固定边：A 完成后一定去 B
        5. compile()                — 编译成可 invoke 的可执行图

    返回值：
        CompiledGraph，可调用 .invoke(initial_state)

    注意：
        每次 build 都会新建图；run_ingest 里用全局单例 _ingest_graph 只 compile 一次。
    """
    graph = StateGraph(IngestState)
    graph.add_node("chunk", _chunk_node)
    graph.add_node("index", _index_node)
    graph.set_entry_point("chunk")
    graph.add_edge("chunk", "index")
    graph.add_edge("index", END)
    return graph.compile()


# 全局单例：避免每次 import 都重新 compile 图（性能 + 行为一致）
_ingest_graph = None


def run_ingest(
    article_id: str,
    title: str,
    content: str,
    source_url: str,
    keyword: str = "",
    author_name: str = "",
) -> dict:
    """
    【入库图 · 对外唯一入口】执行一次完整的「切块 → 向量入库」。

    参数：
        来自 fetch_toutiao_article 或 MySQL 的文章字段，会填入 IngestState 初始值。

    返回：
        invoke 结束后的完整 state（dict），常用字段：
        - documents: 切块列表
        - chunk_count: 入库块数

    调用链示例：
        scripts/import_toutiao_article.py
            → run_ingest(...)
                → _ingest_graph.invoke(initial)
                    → _chunk_node → _index_node

    在整体流程中：
        这是「头条长文进入 RAG 向量库」的最后一步编排。
    """
    global _ingest_graph
    if _ingest_graph is None:
        _ingest_graph = build_ingest_graph()

    initial: IngestState = {
        "article_id": article_id,
        "title": title,
        "content": content,
        "source_url": source_url,
        "keyword": keyword,
        "author_name": author_name,
    }
    return _ingest_graph.invoke(initial)
