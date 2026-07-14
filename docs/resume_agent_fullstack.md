# 【请替换姓名】 · AI 全栈工程师

**手机：** 1xxxxxxxxxx · **邮箱：** xxx@gmail.com · **城市：** 北京 · **GitHub：** github.com/【请替换】

---

## 专业技能

- **前端基础：** 1 年 Vue 业务开发经验（组件化、路由、Axios 联调、Element UI 表单与列表）；独立使用 **React 18 + TypeScript + Vite** 完成 Agent 任务管理前端（鉴权、任务创建、Pipeline 可视化）。
- **后端与工程：** **FastAPI** REST API 设计、**SQLAlchemy 2.0** ORM、**MySQL** 数据建模、**JWT** 鉴权、**APScheduler** 定时任务、Docker Compose 本地编排；熟悉分层架构（API → Service → Agent/Skill）。
- **Prompt 与 Agent 工程：** 设计多 Agent **System Prompt** 与分阶段 Skill 调用策略；实现 **ReAct 式 Function Calling 循环**（模型决策 → Tool 执行 → 结果回注 → 迭代直至终稿）；理解「生成 → 执行 → 校验 → 降级」闭环。
- **AI Agent 开发：** 自研 **3 Agent 顺序编排**（需求理解 → 文案创作 → 审核优化）+ **11 个可插拔 Skill**；**LangGraph StateGraph** 构建 RAG 入库/检索双图；**RAG**（RecursiveCharacterTextSplitter 切块 + Chroma 向量检索 + 本地 Embedding）；热榜自动同步与语义匹配。
- **AI 辅助开发：** 熟练使用 **Cursor** 进行需求拆解、代码生成、重构与 Debug；具备「人类定方向、AI 写实现、人工做质量门禁」的协作式开发习惯。

---

## 工作经历

| 时间 | 公司 / 部门 | 岗位 | 摘要 |
|------|-------------|------|------|
| 【请替换】2024.xx – 2025.xx | 【请替换】xx 科技 | 前端开发工程师 | Vue 2/3 后台与活动页开发；接口联调、组件封装、基础性能与兼容处理 |
| 2022.06 – 2024.06 | — | 自主转型学习 | 系统学习 Python Web、LLM 应用与 Agent 架构；完成多智能体文案生成系统从 0 到 1 的设计与实现 |

> **空窗叙事建议（面试口述，勿写「考研失败」）：** 2022–2024 年聚焦 AI 应用方向自学，2024 年后结合前端经验推进全栈 Agent 项目落地。

---

## 项目经验

### 多智能体热点爆款文案生成系统 · 独立设计与全栈实现

**项目描述：** 面向营销/内容场景的 **Multi-Agent 文案生产平台**。用户提交创作需求后，系统自动匹配热榜话题、检索历史爆款与头条参考文风，经三阶段 Agent 流水线输出可发布文案；支持任务追踪、Agent 执行日志与热榜管理。

**技术栈：** Python 3.12 · FastAPI · DeepSeek API · LangGraph · LangChain · ChromaDB · HuggingFace Embeddings · MySQL · APScheduler · React 18 · TypeScript · Vite · JWT · Docker

**开发方式：** 后端 Agent/RAG 核心自研；前端 React 管理台；使用 **Cursor** 辅助加速 API、Skill 与 LangGraph 图结构迭代。

**项目亮点：**

1. **三 Agent 顺序编排 + 多级降级容错**  
   设计 `AgentOrchestrator` 固定流水线：需求理解 Agent → 文案创作 Agent → 审核优化 Agent。需求解析失败时降级为「原始需求 + 空热点」继续创作；审核失败时自动将初稿升格为终稿，避免单点 Agent 故障导致整单失败。任务状态、Token 消耗、分阶段结果统一写入 MySQL 便于复盘。

2. **ReAct Function Calling 引擎 + 可插拔 Skill 体系**  
   抽象 `BaseAgent._run_loop` 实现标准 ReAct 循环：`tools 列表 → model tool_calls → SkillExecutor 执行 → tool 结果回注 → 直至 finish`。通过 `SkillRegistry` 注册 **11 个 Skill**（需求解析、热榜搜索、平台规则、RAG 检索、大纲/初稿/标签、质量评审/优化、头条参考检索等），各 Agent 按职责子集授权；`max_tool_calls` 上限防止模型工具调用死循环。

3. **LangGraph 双 StateGraph 驱动头条 RAG**  
   离线 **ingest 图**：`chunk → index`，长文 RecursiveCharacterTextSplitter（600 字/块、80 字重叠、中文标点优先切分）→ Chroma 向量入库；在线 **query 图**：`retrieve → format`，Top-K 语义检索 → 格式化为 Agent Prompt 可用的 reference 片段。检索与格式化解耦为独立节点，便于后续替换向量库或调整展示规则。

4. **双路 RAG + 热榜数据闭环**  
   历史爆款文案向量库（创作时 few-shot 参考）+ 头条长文参考库（写法/style 参考）并行增强创作 Agent；APScheduler 每小时同步多平台热榜并触发向量化，创作阶段通过 Skill 自动匹配相关热点话题。

5. **全栈交付与可观测性**  
   FastAPI 提供任务/热榜/用户 REST API；JWT 登录鉴权 + 角色路由；React 前端 `AgentPipeline` 组件可视化三阶段进度；Agent 调用链、Tool 结果、错误信息落库，支持任务详情页排查单次生成全过程。

6. **编排引擎抽象，预留 LangGraph 编排迁移**  
   定义 `OrchestrationEngine` 统一接口，`NativeOrchestrationEngine` 适配现有自研编排器，配置项 `ORCHESTRATION_ENGINE` 支持运行时切换，为后续接入 LangGraph 级 Multi-Agent 编排预留扩展点。

**个人职责：** 系统架构设计、Agent/Skill/RAG 核心实现、数据库建模、API 与前端联调、部署文档与脚本（MySQL 初始化、Docker Compose、头条 RAG 导入脚本）。

**项目地址：** 【请替换 GitHub 链接或「本地项目，可提供 Demo 录屏」】

---

## 其他项目 / 补充（可选，按需保留）

### 【请替换】Vue 后台管理系统 · 前端开发（2024 – 2025）

- 负责【请替换：如活动配置 / 数据报表 / 表单流程】等模块的页面开发与接口联调  
- 封装【请替换：如表格、上传、权限按钮】等通用组件，减少重复代码  
- 配合后端完成【请替换：如分页、导出、表单校验】联调与上线  

---

## 教育背景

| 时间 | 学校 | 专业 | 学历 |
|------|------|------|------|
| 【请替换】2018.09 – 2022.06 | 【请替换】xx 大学 | 【请替换】xx 专业 | 本科 |

---

## 求职意向

**目标岗位：** AI 应用开发工程师 / Agent 工程师 / AI 全栈工程师  
**期望城市：** 北京  
**到岗时间：** 【请替换】

---

## 附：简历使用说明（投递前删除本节）

1. 将所有 **【请替换】** 项改为真实信息；勿保留「考研失败」等负面表述。  
2. 若项目未开源，准备 **3–5 分钟 Demo 录屏**（创建任务 → Pipeline 跑通 → 查看文案与日志）。  
3. 参考模板中的量化表述：可在有真实数据后补充，例如「单次任务平均 Token」「热榜同步平台数」「端到端生成耗时」——**无数据勿编造百分比**。  
4. 投递前建议补 1 条 **LangGraph 开源 PR**（如 docstring 贡献），将链接写入 GitHub 或项目亮点末尾。  
5. 一页纸版本：保留「专业技能 + 1 个项目 + 工作经历 + 教育背景」，删除「附：使用说明」与「其他项目」次要 bullet。
