"""
测试头条 RAG 检索（直接调用 LangGraph query 图，不经过 Agent）
==============================================================

【在整体流程中的位置】
    与 CopywriterAgent 调 Skill 时内部走的链路相同：
        run_rag_query() → retrieve 节点 → format 节点

    本脚本用于开发调试：不启动后端、不消耗 LLM token，只验证向量库是否有数据。

用法：
    python scripts/query_toutiao_rag.py "AI就业 深度分析"
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lang.graph.query_graph import run_rag_query


def main() -> None:
    """
    从命令行读取检索词，invoke query 图，打印 references JSON。
    """
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "AI就业"
    print(f"检索: {query}\n")

    # LangGraph query 图入口：retrieve → format
    result = run_rag_query(query_text=query, top_k=3)

    print(json.dumps(result.get("references") or [], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
