"""
LangChain + LangGraph 层（头条长文 RAG）
=========================================

【本包在整体项目中的位置】

    自研三 Agent（orchestrator）
        ↓
    CopywriterAgent 调 Skill
        ↓
    app/lang/  ← 你在这里
        ├── graph/     LangGraph 流程编排（ingest 图、query 图）
        ├── rag/       LangChain 切块、入库、检索
        ├── embeddings.py / vectorstore.py  向量模型与 Chroma
        └── toutiao_fetcher.py  抓取正文（LangGraph 之前，普通 Python）

【学习顺序建议】
    1. graph/state.py        — State 长什么样
    2. graph/ingest_graph.py — 入库图
    3. graph/query_graph.py  — 检索图
    4. rag/chunking.py 等     — 各节点真正干活的函数
"""
