# Agent Python 全栈开发项目面试话术

> 项目：多智能体热点爆款文案生成系统  
> 目标岗位：Agent 开发工程师 / Python 全栈工程师 / AI 应用开发工程师  
> 使用原则：只讲源码能够证明的事实；个人经历、线上流量和性能数字必须按真实情况补充。

## 一、先记住项目定位

这不是一个“套壳聊天机器人”，而是一个面向内容生产的可控 Agent 工作流系统。

用户提交创作目标后，系统会完成需求理解、热点匹配、资料检索、内容规划、分阶段创作、质量审核、定向重写和结果持久化。系统同时提供 Fast 与 Plan 两种执行模式，并通过重试、反思、质量门禁、Checkpoint、人工接管和审计日志控制 Agent 的不确定性。

一句话定位：

> 我做的是一个 FastAPI + React 的 Agent 全栈应用，核心不是单次调用大模型，而是把需求理解、工具调用、RAG、生成、审核和失败恢复组织成可观测、可恢复、成本有上限的工作流。

## 二、不同时间长度的项目介绍

### 1. 30 秒版本

> 我独立实现了一个多智能体热点文案生成系统，后端使用 FastAPI、SQLAlchemy 和 MySQL，前端使用 React、TypeScript 和 Vite。核心采用需求 Agent、创作 Agent、审核 Agent 与 Lead Agent 协作，并通过 LangGraph 表达分类、规划、执行、质量门禁和人工介入状态。系统还接入了 ChromaDB RAG、热点同步、风格卡、JWT 鉴权、审计日志和 Docker 部署。这个项目让我真正处理了 Agent 工程中的工具调用、状态管理、失败恢复、质量控制和全栈交付问题。

### 2. 1 分钟版本

> 这个项目解决的是内容团队从热点发现到可发布文案的自动化问题。用户在 React 前端提交平台、主题、语气、字数和执行模式，FastAPI 创建任务后交给后台编排。
>
> 快速任务走固定的需求理解、文案创作和审核优化三阶段流水线；复杂任务可以走 Plan 模式，先分类，再由 Planner 生成结构化步骤，Executor 逐步执行。每个 Agent 只能调用授权的 Skill，例如热点搜索、平台规则、RAG 检索、大纲生成、敏感词检查和质量评审。
>
> 为了解决大模型不稳定的问题，我没有让流程无限循环，而是设置了单步重试、有限轮次反思、确定性质量门禁和人工接管。中间状态与 Checkpoint 写入任务的编排元数据，前端能够展示 Pipeline 和审计时间线。RAG 侧使用 LangGraph 拆分入库图和查询图，底层使用 ChromaDB 与本地 Embedding。最终通过 Docker Compose 组织应用和数据库。

### 3. 3 分钟版本

> 项目背景是热点营销文案生产存在三个问题：人工搜集热点慢、不同平台规则不一致、单次大模型生成结果不可控。所以我把问题拆成“获取事实—制定计划—执行工具—质量验证—持久化和展示”五个部分。
>
> 在系统入口上，React 前端负责用户鉴权、任务创建、内容资产管理和执行过程展示；FastAPI 提供任务、用户、热榜、日志和内容资产 API。任务创建后先写入数据库，再通过 BackgroundTasks 启动编排，避免 HTTP 请求一直等待生成完成。
>
> Agent 层有需求理解、文案创作、审核优化和 Lead 四类角色。底层 BaseAgent 实现了类似 ReAct 的工具调用循环：把当前 Agent 可用的 Tool Schema 交给模型，模型返回 tool call，SkillExecutor 执行并把结果回注上下文，直到得到最终输出或达到调用上限。SkillRegistry 当前实际注册 21 个 Skill，并按 Agent 职责做最小权限分配。
>
> 编排有两条路线。Fast 模式使用固定三阶段流水线，延迟和 Token 成本比较可预测；Plan 模式先做任务分类，再生成结构化计划，通过 LangGraph StateGraph 执行每个步骤。失败后先做有限次数重试，仍失败时可以反思并局部回退；最终还要通过质量门禁。门禁只允许一次定向重写，仍不合格就进入 awaiting_human，而不是无限自循环。
>
> RAG 分成入库和查询两张图。入库侧先用 RecursiveCharacterTextSplitter 按中文标点切分，默认 600 字、80 字重叠，再写入 Chroma；查询侧执行 Top-K 检索并格式化为 Agent 可用上下文。内容资产不仅保存原文，还可以抽取标题公式、开头钩子、结构、节奏和 CTA 形成风格卡，并通过重叠检查降低洗稿风险。
>
> 工程方面，我使用 SQLAlchemy 管理用户、任务、文案、Agent 日志、审计和内容资产；使用 JWT 做鉴权；前端展示 Agent Pipeline、质量报告、计划步骤和审计时间线；使用 Docker、Nginx 和 Gunicorn 组织部署。项目目前前端生产构建可以通过，后端 85 项测试中有 78 项通过，剩余 7 项集中在鉴权测试的 SQLite 建表 Fixture 问题，这也是我下一步会修复的工程技术债。

## 三、系统架构怎么讲 

```text
React / TypeScript
  ├─ 登录、任务创建、热榜与内容资产
  └─ Pipeline、质量报告、审计时间线
                ↓ REST API
FastAPI
  ├─ JWT / RBAC / Pydantic
  ├─ Task API + BackgroundTasks
  └─ Service 层
                ↓
OrchestrationEngine
  ├─ Native：固定三阶段流水线
  └─ LangGraph：分类 → 规划 → 执行 → 处理结果 → 质量门禁
                ↓
Agents
  ├─ Requirement Agent
  ├─ Copywriter Agent
  ├─ Reviewer Agent
  └─ Lead Agent
                ↓
SkillRegistry / SkillExecutor
  ├─ 热点、平台规则、RAG
  ├─ 大纲、初稿、标签、保存
  ├─ 质量审核、敏感词、相似度
  └─ Agent 委派与结束任务
                ↓
SQLAlchemy / MySQL + ChromaDB + 审计日志
```

架构设计的核心回答：

> 我把“流程控制”和“业务能力”拆开了。LangGraph 或 Native Engine 决定下一步做什么，Agent 决定如何调用能力，Skill 封装具体工具，Service 和 Repository/ORM 负责业务规则与数据。这种拆分让模型、工作流框架和向量库都可以替换，而不会把所有逻辑绑在 Prompt 里。

## 四、一次请求的完整链路

1. 前端收集主题、平台、语气、字数、风格卡和 Fast/Plan 模式。
2. `POST /api/v1/tasks` 通过 Pydantic 校验并校验当前用户。
3. 后端先创建 Task，写入初始 `orchestration_meta`。
4. FastAPI `BackgroundTasks` 在响应后启动编排。
5. Engine Factory 根据配置选择 Native 或 LangGraph Engine。
6. PipelineState 从 Task 与编排元数据构造统一状态。
7. Fast 模式执行 Requirement → Copywriter → Reviewer。
8. Plan 模式执行 classify → plan → execute_step → handle_outcome。
9. Agent 在 BaseAgent 工具循环中调用被授权的 Skill。
10. 创作 Skill 可调用热点、平台规则、风格卡和 RAG。
11. Verify/Judge 生成质量报告，Policy 给出 finalize、rewrite 或 awaiting_human。
12. 任务状态、终稿、Checkpoint 和审计事件持久化。
13. 前端轮询任务详情，渲染 AgentPipeline、计划步骤和 AuditTimeline。

## 五、最值得强调的六个技术亮点

### 亮点 1：Agent 与 Skill 的职责隔离

话术：

> 我没有给每个 Agent 全部工具，而是按职责授权。需求 Agent 只做需求解析和热点匹配；创作 Agent 使用平台规则、RAG、大纲和写作类 Skill；审核 Agent 使用敏感词、重叠度、质量评审和优化 Skill；Lead Agent 只拥有委派和结束任务能力。这既减少 Tool Schema 噪声，也降低模型误调用高权限工具的概率。

代码依据：

- `app/agents/base_agent.py`：工具调用循环
- `app/skills/base.py`：SkillRegistry 与 SkillExecutor
- `app/skills/__init__.py`：21 个实际注册 Skill 及角色授权列表

容易被追问：

> 为什么旧注释写 10 个 Skill？

回答：

> 最初 MVP 是 10 个，后续增加了头条 RAG、风格卡、合规检查和 Agent 委派能力，实际注册数已经是 21。注释没有同步，这是明确的文档技术债。我不会在面试中把注释当运行事实，后续会把 Skill 元数据改成自动生成文档，避免数量漂移。

### 亮点 2：Fast / Plan 双模式

话术：

> 所有任务都走 Planner 会增加延迟和成本，所以我没有把 Agentic 复杂度强加给简单任务。Fast 模式适合快速预览，采用固定三阶段；Plan 模式适合复杂长文，先分类并生成结构化计划。两种模式共用状态、Agent 和质量门禁，但在控制流复杂度上不同。

权衡：

- Fast：可预测、便宜，但适应复杂任务能力有限。
- Plan：可解释、可局部恢复，但多一次或多次 LLM 调用。
- 系统保存 requested mode 与 resolved mode，便于审计真实执行路径。

### 亮点 3：有边界的失败恢复

话术：

> Agent 系统最危险的不是失败，而是无上限地重试和自我反思。我把恢复分为三层：L1 是单步有限重试；L2 是有限轮次反思并局部回退；L3 是进入 awaiting_human。最终质量门禁也只允许一次定向重写，保证成本上限。

关键配置：

- 单步重试上限：默认 2
- 反思轮次上限：默认 2
- 最终门禁动作：finalize / rewrite / awaiting_human

### 亮点 4：Checkpoint 与人工恢复

话术：

> 当任务进入 awaiting_human 时，我会把当前步骤、计划、中间产物、失败原因和质量门禁结果序列化到 Task 的 JSON 编排元数据中。用户可以选择 retry、接受当前草稿或取消。恢复时不会从头跑整条链路，而是基于 Checkpoint 继续。

为什么暂时使用 JSON 字段：

> 这是 MVP 阶段为了兼容旧表结构和快速演进做的选择。优点是不需要为状态新增很多列；缺点是查询和约束能力弱。规模扩大后我会拆成 execution、checkpoint 和 event 表，并增加版本字段。

### 亮点 5：双路径 RAG

话术：

> 我把 RAG 拆成离线入库和在线查询。入库图负责 chunk 和 index，查询图负责 retrieve 和 format。这样重建索引、替换 Embedding 或调整 Prompt 格式不会互相耦合。默认切块是 600 字、80 字重叠，Top-K 为 3，这些都集中配置。

为什么使用重叠：

> 中文文章的观点经常跨段，完全无重叠会丢失边界上下文；重叠过大又会造成召回内容重复和 Token 浪费，所以需要通过真实语料评估，而不是把当前参数说成最优值。

### 亮点 6：全链路可观测性

话术：

> 我记录的不只是最终文案，还包括 Agent 阶段、工具调用、输入输出摘要、失败级别、计划步骤、重试、反思和质量门禁。前端通过 Pipeline 和 AuditTimeline 展示这些事件。这样出现坏结果时可以定位是检索、Prompt、工具还是编排问题。

## 六、关键难点的 STAR 话术

### 难点 1：如何控制 Agent 无限循环

**S：** 多工具 Agent 可能重复调用工具，复杂工作流也可能持续重试和反思。  
**T：** 保证任务最终收敛，并让单次任务成本有上限。  
**A：** 我在 Agent 工具循环设置调用上限，在编排层设置单步重试和反思轮次，在最终门禁只允许一次定向重写；超过边界则进入人工处理。  
**R：** 控制流从隐式 Prompt 约束变成显式代码策略，失败路径可测试、可审计。当前没有真实线上成本下降百分比，因此不虚构量化收益。

### 难点 2：如何让失败后续跑而不是从头开始

**S：** 长文任务步骤多，如果最后审核失败后全部重跑，会浪费前面已经合格的结果。  
**T：** 支持局部恢复和人工介入。  
**A：** 使用统一 PipelineState，持久化计划、current_step、中间产物和质量报告；恢复接口根据 human action 重建状态，只回到需要重试的步骤。  
**R：** 系统具备 Checkpoint 语义，能够解释“从哪里失败、为什么恢复、恢复后做了什么”。

### 难点 3：如何降低 RAG 洗稿风险

**S：** 参考爆款文章容易让模型复制原句。  
**T：** 既学习结构和风格，又避免直接复用表达。  
**A：** 将参考内容抽象成标题公式、钩子、结构、节奏和 CTA 风格卡；生成后增加文本重叠检查和合规 Skill；参考材料作为上下文而不是终稿模板。  
**R：** 把“模仿原文”转成“复用结构化写作规律”。不过这不是法律意义上的版权保证，仍需人工审核和更严格的相似度评估。

## 七、Agent 与 LangGraph 高频追问

### Q1：为什么要多 Agent，单 Agent 不行吗？

> 单 Agent 当然能做 MVP，但需求理解、创作和审核的目标不同，Prompt 和工具集合也不同。拆分后可以按职责限制工具、独立测试和替换模型。代价是调用次数和状态管理复杂度增加，所以简单任务仍保留固定 Fast 路径。

### Q2：这算真正的 Multi-Agent 吗？

> 系统既有固定的专业 Agent 顺序协作，也有 Lead Agent 通过 delegation Skill 委派专业 Agent。它不是开放式 Agent 社会，而是受控的角色协作系统。我会准确称为“受控 Multi-Agent workflow”。

### Q3：ReAct 在项目里体现在哪里？

> BaseAgent 把工具描述交给模型，读取 tool_calls，执行 Skill，将工具结果作为新消息回注，再让模型继续判断，直到 finish 或达到上限。它具备 Thought/Action/Observation 的工程结构，但不会保存或展示模型隐式思维链，只保存可审计的工具行为和摘要。

### Q4：LangGraph 比普通函数调用好在哪里？

> 普通函数调用适合固定短流程；LangGraph 把状态、节点和条件路由显式化，更适合重试、回退、质量门禁和人工介入。它也让流程图、测试断言和恢复语义更清晰。

### Q5：Native Engine 和 LangGraph Engine 为什么同时存在？

> 我通过 OrchestrationEngine 抽象统一入口，Native 保留成熟的固定编排，LangGraph 承载更复杂的状态图。这样可以灰度迁移和对比，而不是一次性重写全部业务。

### Q6：如何保证 Agent 只能调用合法工具？

> 一是每个 Agent 返回白名单 Skill 名称；二是注册器只给模型暴露对应 Tool Schema；三是 Executor 只执行注册过的名称；四是 Skill 内部继续做参数、权限和业务校验。模型选择工具不等于绕过后端授权。

### Q7：如果模型返回非法 JSON 怎么办？

> Planner、Reflect 等服务先尝试解析结构化输出，失败时使用确定性默认计划或 fallback reflection。核心流程不能把模型格式完全当可信输入。

### Q8：如何防 Prompt Injection？

> 当前已有工具白名单、后端权限和结构化状态边界，但对 RAG 文档中的指令注入还没有完整防线。生产化会增加文档来源信任等级、把检索内容标记为不可信数据、限制工具副作用、加入输出策略检查，并对高风险操作要求人工确认。

### Q9：如何评估 Agent 效果？

> 当前有质量维度、流程测试和审计数据，但还缺离线黄金数据集与长期线上指标。下一步会建立固定任务集，评估任务完成率、工具选择准确率、门禁通过率、人工接管率、平均调用次数、Token 成本、P95 延迟和引用命中质量。

### Q10：为什么不让 Reviewer 一直改到高分？

> Reviewer 本身也是概率模型，无限互评可能造成震荡、内容漂移和不可控成本。系统只允许有边界的定向重写，仍不通过就交给人。

## 八、Python / FastAPI 高频追问

### Q1：为什么选择 FastAPI？

> 它适合类型驱动的 AI API，Pydantic 能做请求校验和契约输出，依赖注入适合数据库会话与鉴权，原生 ASGI 也方便处理外部模型和数据源 I/O。

### Q2：项目真的充分异步吗？

> 不能夸大。API 框架是 ASGI，部分外部调用使用 HTTP 客户端，但 Agent 主链路和 SQLAlchemy 会话仍有同步部分，任务执行目前使用 FastAPI BackgroundTasks。它适合单机 MVP，不等同于可靠的分布式任务队列。

### Q3：BackgroundTasks 有什么限制？

> 它与 Web 进程同生命周期，进程崩溃时任务可能丢失，不支持跨节点调度和完善重试。生产环境应迁移到 Celery、RQ、Dramatiq 或消息队列，并增加幂等键、任务租约和死信处理。

### Q4：数据库事务怎么管理？

> FastAPI 依赖提供请求级 Session，业务写入后显式 commit，异常时需要 rollback。Agent 长任务不适合持有一个超长事务，所以阶段结果和 Checkpoint 应分段提交。

### Q5：JWT 鉴权链路是什么？

> 登录校验密码哈希后签发 JWT；受保护接口通过依赖解析 Bearer Token，验证签名和过期时间，再查询用户并检查 active/admin 状态。前端客户端统一附加 Token，遇到未授权则清理登录态。

### Q6：Pydantic V2 有什么技术债？

> 测试提示部分模型仍使用 class Config，Pydantic V2 已建议 ConfigDict。当前能运行，但应迁移以避免 V3 移除后升级受阻。

### Q7：SQLAlchemy 的关系模型承担什么？

> 关系库保存用户、任务、文案、Agent 日志、审计事件、热点同步和内容资产；向量库只负责语义检索。两者职责不同，不能用 Chroma 替代业务事务库。

### Q8：如何保证任务幂等？

> 当前以任务 ID 驱动状态，但还没有完整的跨进程幂等机制。生产化应为外部触发增加 idempotency key，对每个步骤保存 execution key，并通过唯一约束避免重复落库。

## 九、RAG 高频追问

### Q1：RAG 的完整链路是什么？

> 抓取或导入文章 → 清洗 → 中文友好切块 → Embedding → Chroma 索引 → 查询向量化 → Top-K 召回 → 格式化上下文 → Agent 创作 → 质量与重叠检查。

### Q2：为什么选择 ChromaDB？

> 本地部署简单，适合个人项目和 MVP，能快速验证检索链路。它不是我对大规模生产场景的唯一选择；数据量、并发和多租户增长后可以评估 pgvector、Milvus 或 Elasticsearch。

### Q3：如何避免检索结果不相关？

> 当前主要依靠向量相似度和 Top-K。进一步会增加 metadata filter、关键词与向量混合检索、Cross-Encoder rerank、最低相似度阈值和引用质量评估。

### Q4：为什么入库图和查询图分开？

> 两条链路的触发时机和扩缩容特征不同。入库关注切块、去重、索引一致性；查询关注低延迟召回和上下文预算，拆分后更容易独立测试与替换。

### Q5：Embedding 模型怎么选？

> 当前使用本地多语言 Sentence Transformer，优点是数据不出本机、无按次费用；缺点是模型加载和 CPU 推理成本。生产环境需要基于中文语料召回指标、延迟和成本做选择，而不是只比较榜单分数。

## 十、React 全栈追问

### Q1：前端在 Agent 项目里不只是表单吗？

> 不只是。它负责鉴权、任务参数、Fast/Plan 模式、风格卡选择、任务状态轮询、Pipeline 展示、质量报告、计划步骤和审计时间线。Agent 系统的可解释性需要前端把内部状态转成用户能理解的反馈。

### Q2：为什么没有 WebSocket？

> 当前使用轮询降低实现复杂度，适合 MVP。任务量和实时性要求上升后会改为 SSE 或 WebSocket；单向状态更新优先考虑 SSE，交互式人工介入再考虑 WebSocket。

### Q3：前端如何处理鉴权？

> AuthContext 维护用户状态，ProtectedRoute 与 AdminRoute 做页面级保护，API Client 统一附加 Token 和处理错误。但真正的权限边界仍在后端，前端路由保护只是体验层。

### Q4：TypeScript 带来了什么价值？

> API 类型覆盖 Task、编排元数据、质量报告和审计事件，能减少复杂 Agent 状态在页面层的字段误用。当前仍是手写类型，后续可从 OpenAPI 自动生成客户端类型，降低前后端契约漂移。

## 十一、工程化与测试怎么回答

当前真实验证结果：

- 前端：`tsc --noEmit && vite build` 通过。
- 后端：85 项测试中 78 项通过、7 项失败。
- 失败范围：`tests/test_auth.py`。
- 直接原因：SQLite 测试连接中没有创建 `users` 表。
- 伴随技术债：Pydantic V2 `class Config` 弃用警告、`datetime.utcnow()` 弃用警告。

推荐话术：

> 项目已经覆盖 Agent 流水线、编排策略、反思、审计、合规、内容资产和长文质量门禁等测试。最近一次全量执行是 85 项中 78 项通过。7 项鉴权测试失败的原因是测试 Fixture 没有在被接口依赖实际使用的 SQLite Engine 上建表，属于测试隔离配置问题。我会通过统一 dependency override、在 fixture 中对同一个 Engine 执行 metadata.create_all，并在 teardown drop_all 来修复。我不会把当前状态描述成测试全绿。

如果问“这是不是代码 Bug”：

> 当前堆栈显示业务查询到达了 SQLite，但表不存在，因此首先是测试数据库初始化/依赖覆盖问题。修复 Fixture 后仍需重跑，不能在重跑前武断地断言业务代码一定没有问题。

## 十二、项目不足与升级路线

主动承认以下不足反而更可信：

1. BackgroundTasks 不适合可靠分布式长任务。
2. Checkpoint 暂存在 Task JSON 字段，缺少独立事件表和版本迁移。
3. RAG 只有基础向量召回，缺少 rerank 与系统化评测。
4. 缺少真实线上 P95、Token 成本和人工接管率数据。
5. RAG Prompt Injection 防护仍需完善。
6. 前端状态采用轮询，实时性一般。
7. Skill 数量注释与实际注册数量不一致。
8. 鉴权测试 Fixture 当前有 7 项失败。
9. 部分 Pydantic 和时间 API 存在弃用警告。
10. 尚未实现跨进程幂等、消息队列、分布式锁和多租户向量隔离。

生产化升级顺序：

1. 先修复测试隔离和所有弃用警告。
2. 将 BackgroundTasks 迁移到可靠队列。
3. 拆分 Execution、Checkpoint、Audit Event 数据模型。
4. 增加幂等键、任务租约、超时和死信队列。
5. 建立 Agent/RAG 离线评测集与成本看板。
6. 增加混合检索、rerank、引用与 Prompt Injection 防护。
7. 使用 SSE 推送执行事件。
8. 增加 OpenTelemetry、Prometheus 指标和结构化 Trace。

## 十三、面试官压力追问

### “这不就是调用 API 吗？”

> 如果只是调用一次模型 API，确实不构成 Agent 工程。我的工作量主要在工具协议、角色权限、状态图、失败恢复、RAG、质量门禁、人工介入、审计以及全栈交付。模型 API 只是其中一个可替换依赖。

### “为什么不用一个超长 Prompt？”

> 超长 Prompt 难以测试、无法局部恢复、工具权限不清晰，而且每次都重复传输上下文。把流程和能力拆开后，可以按需检索、按阶段验证并保存中间状态。

### “你用了 AI 辅助写代码，哪些是你真正掌握的？”

> AI 可以加速样板代码，但架构边界、状态模型、失败策略、数据契约、测试判断和最终验收必须由我负责。我能够从任务 API 一直解释到 Engine、Agent、Skill、RAG、ORM 和 React 页面，并说明每个选择的权衡和现有缺陷。

### “项目有真实用户吗？”

> 请按真实情况回答。如果没有线上用户：目前是可运行的个人项目和工程验证，不伪造 DAU、转化率或节省比例。价值主要通过完整链路、测试、Demo 和可解释设计证明。

### “你项目里最大的失误是什么？”

> Skill 从 10 个扩展到 21 个后，文档注释没有同步；另外鉴权测试的数据库 Fixture 也暴露了依赖覆盖不统一的问题。这说明可执行事实不应该依赖手写注释，测试基础设施也要与生产依赖注入保持同一入口。我会用自动生成 Skill 清单和统一测试 App Factory 解决。

## 十四、简历项目描述

> **多智能体热点爆款文案生成系统｜独立设计与全栈实现**  
> 基于 FastAPI、React、LangGraph、SQLAlchemy、MySQL、ChromaDB 和 DeepSeek API 构建可控 Multi-Agent 内容生产平台；实现需求理解、创作、审核与 Lead Agent 协作，以及按职责授权的可插拔 Skill 体系。设计 Fast/Plan 双模式编排、单步重试、有限反思、确定性质量门禁、Checkpoint 与人工恢复，支持任务执行审计和前端 Pipeline 可视化。实现中文长文 RAG 入库/查询双图、内容风格卡与重叠检查，并通过 Docker Compose、Nginx 和 Gunicorn 完成工程化交付。

不要写入没有证据的数据：

- “性能提升 80%”
- “日活上万”
- “准确率 95%”
- “节省人工成本 70%”
- “支持百万级向量”

## 十五、面试前练习顺序

第一轮：只练 30 秒和 1 分钟介绍，做到不背诵腔。  
第二轮：画出完整请求链路，能从 React 一直讲到数据库。  
第三轮：重点练 Fast/Plan、ReAct、LangGraph、RAG 和失败恢复。  
第四轮：主动讲测试现状和项目不足。  
第五轮：让对方连续追问“为什么”，每个设计至少能说出一个优点、一个缺点和一个替代方案。

最后的收尾话术：

> 这个项目让我从“会调用模型”走到了“能交付 Agent 系统”。我现在重点关注的不是让模型表现得更聪明，而是怎样通过状态、工具、数据、评测和人工边界，让它在真实业务里更可靠。我希望下一份工作继续做 Agent Python 全栈开发，把这套 MVP 经验推进到消息队列、分布式执行、系统化评测和生产可观测性。

## 十六、源码证据索引

- FastAPI 应用入口：`app/main.py`
- 任务创建与后台执行：`app/api/v1/tasks.py`
- ReAct 工具循环：`app/agents/base_agent.py`
- Fast 三阶段执行：`app/agents/pipeline_runners.py`
- Plan、重试、反思与恢复：`app/agents/agentic_runners.py`
- LangGraph Agent 状态图：`app/lang/graph/agentic_pipeline_graph.py`
- Skill 注册和权限子集：`app/skills/__init__.py`
- Skill 注册器与执行器：`app/skills/base.py`
- 最终质量门禁策略：`app/services/orchestration_policy.py`
- Checkpoint 持久化：`app/services/orchestration_persistence.py`
- RAG 中文切块：`app/lang/rag/chunking.py`
- RAG 入库图：`app/lang/graph/ingest_graph.py`
- RAG 查询图：`app/lang/graph/query_graph.py`
- ORM 任务状态：`app/models/task.py`
- React Pipeline：`frontend/src/components/AgentPipeline.tsx`
- React 审计时间线：`frontend/src/components/AuditTimeline.tsx`
- 任务详情页：`frontend/src/pages/TaskDetail.tsx`
- 部署：`Dockerfile`、`docker-compose.yml`、`nginx.conf`

