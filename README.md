# 多智能体热点文案生成系统

一个面向热点营销场景的 AI Agent 全栈项目。系统将热点采集、需求分析、内容生成、质量审核和结果追踪组织为可观测、可恢复的工作流，并提供 React 管理端与 FastAPI API。

> 核心技术：FastAPI · React · TypeScript · LangGraph · DeepSeek · RAG · ChromaDB · MySQL · Docker

## 项目亮点

- **多 Agent 协作**：需求分析、文案创作、审核优化三个角色分工协作，避免单次 Prompt 难以控制质量的问题。
- **双编排引擎**：通过统一接口在自研 Native 引擎与 LangGraph 状态图之间切换，支持灰度验证与快速回退。
- **三种执行模式**：Fixed 适合稳定流水线，Agentic 提供 Plan & Execute，Lead 支持主 Agent 动态委派子任务。
- **有边界的质量闭环**：对生成结果执行确定性质量门禁，仅定向重写低分章节；超过重试边界后进入人工处理，控制 Token 成本并避免无限循环。
- **RAG 内容资产库**：支持导入参考文章、语义检索、提取写作模式并沉淀为风格卡，在生成任务中复用。
- **全链路可观测**：记录各阶段状态、耗时、输入输出摘要、重试与回退原因，前端以执行流水线和审计时间线展示。
- **工程化交付**：包含 JWT 鉴权、RBAC、后台任务、定时热榜同步、测试、Docker Compose、Nginx 和健康检查。

## 工作流程

```text
用户需求 + 实时热点 / 内容资产
              │
              ▼
         需求理解 Agent
      意图解析 · 平台适配 · 热点匹配
              │
              ▼
         文案创作 Agent
      Brief · 提纲 · RAG · 分段生成
              │
              ▼
         审核优化 Agent
      质量评分 · 合规检查 · 定向重写
              │
        ┌─────┴─────┐
        ▼           ▼
     完成并入库   awaiting_human
                    人工确认后恢复
```

## 功能概览

| 模块 | 能力 |
| --- | --- |
| 热点中心 | 聚合热榜、手动同步、关键词搜索与向量化 |
| 内容生成 | 创建异步任务，支持多平台、字数和风格配置 |
| 头条长文 | 生成 Content Brief、结构化提纲和分章节正文 |
| 内容资产 | 导入参考文章、重新索引、语义检索、生成风格卡 |
| Agent 编排 | Native / LangGraph 引擎，Fixed / Agentic / Lead 模式 |
| 质量控制 | 多维评分、合规检查、局部反思与有限重试 |
| 任务追踪 | 阶段进度、执行日志、审计时间线与人工恢复 |
| 用户系统 | 注册登录、JWT 鉴权、个人资料和管理员权限 |

## 技术架构

| 层次 | 技术选型 |
| --- | --- |
| 前端 | React 18、TypeScript、Vite、React Router |
| API | FastAPI、Pydantic、Uvicorn / Gunicorn |
| Agent | DeepSeek（OpenAI-compatible API）、自定义 Skill、LangGraph |
| RAG | LangChain、ChromaDB、Sentence Transformers |
| 数据 | MySQL 8、SQLAlchemy 2 |
| 基础设施 | Docker、Docker Compose、Nginx、APScheduler |
| 测试 | Pytest、FastAPI TestClient、前端 TypeScript 构建检查 |

系统通过 `OrchestrationEngine` 抽象隔离业务与编排实现。API 只依赖统一接口，运行时根据配置选择 Native 或 LangGraph 引擎；Agent 决定“做什么”，Skill 封装“如何做”，数据层负责保存业务结果与审计证据。

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- MySQL 8（或使用 Docker Compose）
- DeepSeek API Key

### 方式一：Docker Compose

```bash
git clone https://github.com/sans923/multi-agent-hot-copy-generator.git
cd multi-agent-hot-copy-generator

cp .env.example .env
# 编辑 .env，至少填写 SECRET_KEY、DEEPSEEK_API_KEY 和 JUHE_API_KEY

docker compose up -d --build
docker compose exec app python scripts/setup_mysql.py
```

启动后访问：

- API 文档：<http://localhost/docs>
- 健康检查：<http://localhost/health>

### 方式二：本地开发

```bash
git clone https://github.com/sans923/multi-agent-hot-copy-generator.git
cd multi-agent-hot-copy-generator

python -m venv venv
```

Windows：

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts/setup_mysql.py
python run.py
```

macOS / Linux：

```bash
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/setup_mysql.py
python run.py
```

另开终端启动前端：

```bash
npm run install:frontend
npm run dev
```

访问地址：

- Web 管理端：<http://localhost:5173>
- Swagger UI：<http://localhost:8000/docs>
- ReDoc：<http://localhost:8000/redoc>

## 核心配置

复制 `.env.example` 为 `.env` 后，按需调整：

```dotenv
# 必填
SECRET_KEY=replace-with-a-random-secret
DEEPSEEK_API_KEY=your-deepseek-api-key
JUHE_API_KEY=your-juhe-api-key

# 编排引擎：native | langgraph
ORCHESTRATION_ENGINE=native

# 执行模式：fixed | agentic | lead
ORCHESTRATION_MODE=fixed

# MySQL
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=copygen
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=copy_generator
```

`.env` 包含密钥和数据库凭据，请勿提交到 Git。

## 测试与构建

```bash
# 后端行为测试
pytest tests -q

# 前端类型检查与生产构建
npm run build
```

测试覆盖鉴权、内容资产 API、Agent 编排、质量策略、反思机制、审计链路、Lead Agent 与长文流水线等核心行为。

## 项目结构

```text
multi-agent-hot-copy-generator/
├── app/
│   ├── agents/             # Agent 角色、运行器与流水线状态
│   ├── api/v1/             # REST API：鉴权、任务、热榜、日志、内容资产
│   ├── lang/               # LangGraph、RAG、向量库与 Embedding
│   ├── orchestration/      # 双编排引擎抽象、工厂与实现
│   ├── services/           # 规划、质量门禁、审计、持久化等领域服务
│   ├── skills/             # 可复用的文案、检索、合规与平台 Skill
│   ├── models/             # SQLAlchemy 模型
│   └── schemas/            # Pydantic 数据契约
├── frontend/src/
│   ├── pages/              # 登录、热榜、任务、内容资产等页面
│   ├── components/         # Agent 流水线、审计时间线等组件
│   ├── api/                # 前端 API 客户端
│   └── contexts/           # 鉴权与全局提示状态
├── tests/                  # 后端自动化测试
├── scripts/                # 数据库初始化、迁移、导入与调试脚本
├── Dockerfile
├── docker-compose.yml
└── nginx.conf
```

## 关键设计取舍

1. **编排实现可替换**：工厂与统一协议降低业务代码对具体框架的依赖，便于比较自研流程和 LangGraph。
2. **循环必须有上限**：规划步数、单步重试、反思轮次和超时均可配置；质量未达标时转人工，而不是无限消耗模型调用。
3. **审计与业务数据分离**：任务表保存业务状态，独立审计表保存执行证据，兼顾查询效率、故障排查和可追溯性。
4. **RAG 与风格规则结合**：语义检索提供事实与范例，结构化风格卡约束标题、钩子、节奏和 CTA，减少仅靠长 Prompt 带来的不稳定性。

## 可继续演进

- 增加 SSE / WebSocket，实时推送 Agent 执行状态
- 引入 Alembic 统一数据库版本管理
- 增加模型调用成本、延迟和质量指标看板
- 扩展微信公众号、小红书等平台的专属生成策略
- 补充 Playwright 端到端测试与 CI/CD

## 说明

本项目用于展示 AI Agent 工作流设计、RAG 应用和 Python + React 全栈工程能力。运行完整生成链路需要自行配置第三方 API Key；请勿将生产密钥或真实用户数据提交到公开仓库。

## License

仅供学习、交流与作品展示。商业使用前请确认所使用模型、数据源及第三方服务的许可条款。
