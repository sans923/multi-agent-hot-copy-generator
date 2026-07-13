"""
LangChain RAG 工具函数包（被 LangGraph 各节点调用）
==================================================

【与 graph/ 的关系】
    LangGraph 节点函数本身很薄，真正逻辑在本包：

    ingest 图 _chunk_node  → rag/chunking.article_to_documents
    ingest 图 _index_node  → rag/ingest.ingest_documents
    query 图 _retrieve_node → rag/retriever.retrieve_toutiao_references
    query 图 _format_node    → rag/retriever.format_references_for_prompt
"""
