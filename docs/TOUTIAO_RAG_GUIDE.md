# 头条长文 RAG 实战指南（LangChain + LangGraph）

> 目标：从今日头条抓取长文 → 切块向量化 → 创作时 RAG 检索写法 → 结合热榜生成文案。  
> 面试：能讲清架构、每段代码职责、LangChain vs LangGraph 分工。

---

## 一、整体架构（必背）

```
                    ┌─────────────────────────────────────┐
                    │  用户创建文案任务（FastAPI）           │
                    └──────────────────┬──────────────────┘
                                       ▼
              ┌────────────────────────────────────────────┐
              │  AgentOrchestrator（自研三 Agent 流水线）    │
              │  需求理解 → 文案创作 → 审核优化              │
              └──────────────────┬─────────────────────────┘
                                 ▼
              ┌────────────────────────────────────────────┐
              │  CopywriterAgent（Function Calling 循环）  │
              │  调用 Skill：search_toutiao_references     │
              └──────────────────┬─────────────────────────┘
                                 ▼
              ┌────────────────────────────────────────────┐
              │  LangGraph query 图：retrieve → format      │
              └──────────────────┬─────────────────────────┘
                                 ▼
              ┌────────────────────────────────────────────┐
              │  LangChain Retriever + Chroma 向量库        │
              │  collection: toutiao_references             │
              └────────────────────────────────────────────┘

入库链路（离线/脚本）：

  头条 URL → toutiao_fetcher → MySQL(toutiao_reference)
           → LangGraph ingest 图：chunk → index
           → Chroma 向量库
```

### LangChain 负责什么？

| 组件 | 文件 | 作用 |
|------|------|------|
| Document | `lang/rag/chunking.py` | 标准文档对象（正文 + metadata） |
| TextSplitter | `lang/rag/chunking.py` | 长文切块（600 字/块，重叠 80） |
| Embeddings | `lang/embeddings.py` | 文本 → 384 维向量 |
| VectorStore | `lang/vectorstore.py` | Chroma 持久化 |
| Retriever | `lang/rag/retriever.py` | similarity_search 语义检索 |

### LangGraph 负责什么？

| 图 | 文件 | 节点 |
|----|------|------|
| **ingest 图** | `lang/graph/ingest_graph.py` | chunk → index |
| **query 图** | `lang/graph/query_graph.py` | retrieve → format |

**面试一句话**：LangChain 做 RAG 的「数据与向量」；LangGraph 做「入库/检索流程编排」；自研 Agent 做「业务与工具调用」。

---

## 二、一步步操作（你要亲手跑）

### Step 0：安装依赖

```powershell
cd d:\demo_project\multi-agent-hot-copy-generator
pip install -r requirements.txt
python scripts/setup_mysql.py
```

首次会向 HuggingFace 下载 Embedding 模型（约 500MB）。

### Step 1：导入一篇头条长文

```powershell
python scripts/import_toutiao_article.py ^
  --url "https://www.toutiao.com/article/7434425099895210546/" ^
  --keyword "AI就业"
```

成功输出：`chunks=N`（N > 0）。

### Step 2：单独测 RAG 检索

```powershell
python scripts/query_toutiao_rag.py "AI就业 深度分析"
```

应返回 JSON 数组，含 `title`、`content_preview`。

### Step 3：走完整创作任务

1. 启动后端 `python run.py`
2. 前端创建任务，platform 选 douyin/weibo 均可
3. 看日志是否出现 `search_toutiao_references` 工具调用

---

## 三、文件清单与面试讲法

### 1. `app/models/toutiao_reference.py`

- **是什么**：MySQL 表，存原文（title/content），向量化状态 embedding_status。
- **为什么要有 MySQL**：向量库只存切块，原文要可追溯、可重新 ingest、可展示来源 URL。
- **面试**：「双存储：MySQL 管元数据与全文，Chroma 管检索用的向量块。」

### 2. `app/lang/toutiao_fetcher.py`

- **是什么**：httpx 抓 HTML，从 `RENDER_DATA` JSON 解析正文。
- **失败怎么办**：换 URL、加 Cookie、或用 [NewsCrawler](https://github.com/NanmiCoder/NewsCrawlerCollection) 抓完手动 import。
- **面试**：「采集层与 RAG 层解耦，fetcher 只负责结构化 {title, content}。」

### 3. `app/lang/rag/chunking.py`

- **RecursiveCharacterTextSplitter**：按 `\n\n`、句号等切，避免句中断开。
- **chunk_size=600, overlap=80**：块太大检索不精准，太小丢上下文；重叠防止边界信息丢失。
- **metadata**：article_id、chunk_index、platform=toutiao，便于过滤和溯源。

### 4. `app/lang/rag/ingest.py`

- **delete_article_chunks**：同一文章重新入库先删旧块，防重复。
- **add_documents**：LangChain 自动调 embedding 写入 Chroma。

### 5. `app/lang/graph/ingest_graph.py`

```text
chunk 节点：article_to_documents()
index 节点：ingest_documents()
```

- **为什么用图**：以后可加「LLM 抽写法摘要」「质量打分过滤」节点，不用改一堆 if。
- **面试**：「ingest 是确定性 DAG，不是 ReAct Agent。」

### 6. `app/lang/graph/query_graph.py`

```text
retrieve 节点：similarity_search
format 节点：转成 Agent 可读的 references 列表
```

### 7. `app/skills/toutiao_rag_skills.py`

- **适配器模式**：BaseAgent 只认 Skill；内部 `run_rag_query()` 调 LangGraph。
- **面试**：「不让 Agent 直接 import langgraph，保持现有 SkillRegistry 架构。」

### 8. `app/agents/copywriter_agent.py`

- prompt 增加：先 `search_toutiao_references`，再 `search_similar_copies`。
- **热点**仍来自 `search_hotlist`（需求 Agent）；**写法**来自头条 RAG。

---

## 四、3 分钟面试项目介绍稿

> 我做的是多 Agent 热点文案系统。热点来自定时同步的热榜并向量化；写法参考来自**头条长文 RAG**。  
> 入库时我用 **LangGraph** 编排 chunk 和 index 两步；检索时用 query 图做 retrieve 和 format。  
> 向量层用 **LangChain** 的 Document、Splitter、HuggingFace Embeddings 和 Chroma。  
> 创作 Agent 还是自研的 Function Calling 循环，通过 `search_toutiao_references` Skill 调用 RAG，再结合热榜生成平台化文案。  
> 这样热点与写法分离：热榜保证时效，头条长文保证结构和深度。

---

## 五、常见面试追问

**Q：为什么不用 LangChain 一把梭 Agent？**  
A：现有三 Agent 编排、日志、降级已稳定；RAG 用 LangChain/LangGraph 局部增强，风险小、可回滚。

**Q：Embedding 为什么用本地模型？**  
A：与原有 embedding_service 一致，免费、离线；生产可换 DeepSeek/OpenAI Embedding，但要统一入库和检索模型。

**Q：chunk_size 怎么定？**  
A：600 字左右适合中文资讯长文；调参看检索 hit 的 content_preview 是否包含完整论点。

**Q：头条写法和抖音文案不一致怎么办？**  
A：RAG 学结构和论证；platform rules + prompt 要求改口语短句；二期可再加抖音 article 库。

**Q：LangGraph 和 if/else 区别？**  
A：图显式表达节点与边，易扩展 HITL、重试、并行；状态 TypedDict 可 checkpoint 断点续跑。

---

## 六、批量导入（可选）

建 `urls.txt`，每行一个头条链接：

```powershell
Get-Content urls.txt | ForEach-Object {
  python scripts/import_toutiao_article.py --url $_ --keyword "你的赛道"
  Start-Sleep -Seconds 2
}
```

---

## 七、故障排查

| 现象 | 处理 |
|------|------|
| 抓取正文失败 | 换文章 URL；或用 NewsCrawler 导出 JSON 再写 import |
| query 结果为空 | 先 import；查 `SELECT * FROM toutiao_reference` |
| 模型下载慢 | 设置 HF 镜像或提前下载 MiniLM |
| Chroma 冲突 | 删除 `./data/chroma` 下 collection 或换 TOUTIAO_RAG_COLLECTION 名 |
