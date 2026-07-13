"""
LangGraph 状态（State）定义
===========================

【State 是什么？】
    LangGraph 里所有节点共用的「记事本」。
    每个节点：读取 state → 执行逻辑 → 返回要更新的字段 → 框架自动合并进 state。

【为什么分两个 State？】
    - IngestState：入库流水线专用（有 title、content、documents 等）
    - QueryState：检索流水线专用（有 query_text、references 等）
    两张图各用各的 state，避免字段混在一起。

【TypedDict + total=False 含义】
    - TypedDict：给 state 字段起名、标注类型，IDE 和阅读代码更清晰
    - total=False：字段不是一开始就必须全有，可以 invoke 时只传一部分，后面节点再补
"""

from typing import TypedDict

from langchain_core.documents import Document


class IngestState(TypedDict, total=False):
    """
    头条长文【入库图】的状态结构。

    在整体流程中的角色：
        import 脚本抓取正文后，把文章信息放进这个 state，
        然后 ingest 图从 chunk 节点开始，一路写到 chunk_count。

    字段生命周期（典型一次 invoke）：
        初始传入：article_id, title, content, source_url, keyword, author_name
        chunk 节点写入：documents（切块后的 LangChain Document 列表）
        index 节点写入：chunk_count（写入向量库的块数）
        可选：error（若某节点失败可写入，供后续条件边使用，当前未启用）
    """

    article_id: str       # 头条文章 ID，唯一标识，也用于 Chroma 里 metadata 过滤
    title: str            # 文章标题，切块时会拼进每块正文头部
    content: str          # 文章全文，chunk 节点的输入
    source_url: str       # 原文链接，写入 metadata 便于溯源
    keyword: str          # 采集时的搜索关键词，便于按赛道过滤
    author_name: str      # 作者名，可选，写入 metadata
    documents: list[Document]  # chunk 节点产出：LangChain 文档块列表
    chunk_count: int      # index 节点产出：实际入库的块数量
    error: str            # 预留：错误信息（扩展条件边、重试时用）


class QueryState(TypedDict, total=False):
    """
    头条长文【检索图】的状态结构。

    在整体流程中的角色：
        创作 Agent 通过 Skill 传入 query_text，
        query 图检索向量库并 format 成 references，供大模型当「写法参考」。

    字段生命周期（典型一次 invoke）：
        初始传入：query_text, top_k
        retrieve 节点写入：documents（向量检索命中的 Document 列表）
        format 节点写入：references（给 Agent/前端用的 dict 列表）
    """

    query_text: str           # 检索问句，如「AI就业 深度分析」
    top_k: int                # 返回几条最相似切块，默认见 settings.RAG_TOP_K
    documents: list[Document] # retrieve 节点产出：原始检索结果
    references: list[dict]    # format 节点产出：格式化后的参考片段
    error: str                # 预留：检索失败时的错误信息
