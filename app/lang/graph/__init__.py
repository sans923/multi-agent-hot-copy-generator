"""
LangGraph 图定义包
==================

【本包在整体流程中的位置】
    头条长文 RAG 的「流程编排层」：只负责规定步骤顺序，不负责具体向量算法。

【包含四张图】
    1. ingest_graph        — 离线入库：chunk → index
    2. query_graph         — 在线检索：retrieve → format
    3. copy_pipeline_graph — 文案主流程（fixed）：requirement → copywriter → reviewer
    4. agentic_pipeline_graph — Agentic（agentic 模式）：classify → plan → execute
    5. lead_pipeline_graph — Lead 总控（lead 模式）：lead → END

【谁调用本包】
    - scripts/import_toutiao_article.py  → run_ingest()
    - app/skills/toutiao_rag_skills.py   → run_rag_query()
    - scripts/query_toutiao_rag.py       → run_rag_query()（测试用）

【与 LangChain 的分工】
    LangGraph：管「先做什么、后做什么」
    LangChain（app/lang/rag/）：管 Document、切块、Embedding、Chroma 读写
"""
