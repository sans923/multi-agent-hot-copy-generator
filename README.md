# 多智能体热点爆款文案生成系统

> 基于 FastAPI + DeepSeek + ChromaDB 的多智能体协作系统，自动抓取热榜话题，生成高质量营销文案

## 系统架构

```
用户请求
    ↓
需求理解 Agent（解析意图 + 热点匹配）
    ↓
文案创作 Agent（调用 10 个 Skill 生成初稿）
    ↓
审核优化 Agent（评分 + 优化，最多迭代1次）
    ↓
返回最终文案
```

## 今日头条长文 MVP

今日头条任务使用一条可解释、成本有上限的长文流水线：

```text
需求解析 + 热点
    → Content Brief（读者、目标、关键词、字数）
    → 结构化提纲（至少 3 个章节，独立章节 ID 与字数预算）
    → 头条 RAG + 按提纲分节创作
    → 五维质量门禁
    → 仅对低分章节定向优化一次
    → 保存终稿、质量报告与审计轨迹
```

任务详情页会展示 Brief、章节提纲、质量维度和重写记录。领域规则集中在
`app/services/longform_mvp_service.py`，保持无数据库、无网络依赖，便于独立测试。

### Fast / Plan 双模式

创建任务时可按成本与质量目标选择执行方式：

- `Fast`：固定三阶段流水线，适合快速预览和低成本生成。
- `Plan`：Lead 生成结构化计划，Executor 按步执行；允许可复用业务步骤跳过、单步失败重试和一次局部反思回退，但验证与审核步骤不可跳过。
- Plan 的终稿必须通过确定性质量门控。若存在低分章节，仅允许一次定向重写；仍未通过则转为 `awaiting_human`，避免无限循环和不可控成本。

任务详情页会展示计划来源、执行步骤、跳过/重试/回退原因以及最终门控结果。产品模式保存在每个任务的 `orchestration_meta` 中，无需新增数据库列；旧任务仍兼容全局编排配置。

### 内容资产库

管理员可从前端导航进入“内容资产”，完成一条可运营的 RAG 数据闭环：

1. 粘贴今日头条文章 URL，填写关键词和互动量。
2. 后端抓取正文并写入 `toutiao_reference`，通过 LangGraph 切块后写入 Chroma。
3. 选择 1～3 篇参考文章，调用 Pattern 模型提取标题公式、钩子、结构、节奏和 CTA，并通过文本重叠检查防止洗稿。
4. 将规律保存为风格卡；创建今日头条任务时可指定风格卡，Copywriter 会优先使用其结构化规则。

管理接口位于 `/api/v1/content-assets`，导入、重索引、删除和生成风格卡均要求管理员权限；普通登录用户可读取风格卡用于创建任务。

已有 MySQL 数据库升级后需执行：

```powershell
mysql -u root -p copy_generator < scripts/migrate_add_toutiao_platform.sql
```

## 技术栈


| 层次     | 技术                    |
| ------ | --------------------- |
| Web 框架 | FastAPI               |
| 大模型    | DeepSeek API          |
| 向量数据库  | ChromaDB              |
| 关系数据库  | MySQL 8（PyMySQL 驱动） |
| 热榜数据   | 韩小韩免费 API             |
| 定时任务   | APScheduler           |
| 部署     | 火山引擎 ECS + Nginx      |


## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
copy .env.example .env
```

编辑 `.env`，至少配置：
- `SECRET_KEY`
- `DEEPSEEK_API_KEY`
- `MYSQL_*`（MySQL 连接信息，见下方）

### 3. 初始化 MySQL

**方式 A：本机已安装 MySQL**

```powershell
# 1. 创建数据库和用户（按提示输入 root 密码）
mysql -u root -p < scripts/init_mysql.sql

# 2. 安装 Python 依赖并建表
pip install -r requirements.txt
python scripts/setup_mysql.py

# 3. （可选）写入测试用户
python scripts/seed_users.py
```

**方式 B：Docker 一键启动 MySQL + 应用**

```bash
docker-compose up -d
docker-compose exec app python scripts/setup_mysql.py
docker-compose exec app python scripts/seed_users.py
```

### 4. 启动服务

```bash
python run.py
```

访问 [http://localhost:8000/docs](http://localhost:8000/docs) 查看 API 文档

### 5. 启动前端（可选）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 [http://localhost:5173](http://localhost:5173)，通过 Vite 代理访问后端 API。

### 6. 运行测试

```powershell
pytest tests -q
cd frontend
npm run build
```

```bash
pip install pytest httpx
pytest tests/ -v
```

## 项目结构

```
multi-agent-hot-copy-generator/
├── frontend/              # React + Vite 前端
│   └── src/               # 页面、API 封装、鉴权
├── app/
│   ├── main.py            # FastAPI 应用入口
│   ├── config.py          # 配置管理
│   ├── database.py        # 数据库连接
│   ├── models/            # SQLAlchemy ORM 模型（6张表）
│   │   ├── user.py        # 用户表
│   │   ├── task.py        # 任务表
│   │   ├── document.py    # 文档表
│   │   ├── copy.py        # 文案表
│   │   ├── agent_log.py   # Agent执行日志表
│   │   └── hotlist_sync.py # 热榜同步表
│   ├── schemas/           # Pydantic 数据校验模型
│   ├── api/v1/            # API 路由
│   │   ├── auth.py        # 注册/登录接口
│   │   └── users.py       # 用户管理接口
│   ├── core/
│   │   ├── security.py    # JWT + 密码哈希
│   │   └── deps.py        # FastAPI 依赖注入
│   └── utils/
│       └── logger.py      # 统一日志
├── tests/                 # 单元测试
├── data/                  # 数据目录（自动创建，不提交 git）
├── logs/                  # 日志目录（自动创建，不提交 git）
├── .env                   # 环境变量（不提交 git！）
├── .env.example           # 环境变量模板
├── requirements.txt       # Python 依赖
└── run.py                 # 启动入口
```

## 开发进度

- Phase 1（Day 1-3）：项目初始化 + 数据库建表 + FastAPI框架 + 用户鉴权
- Phase 2（Day 4-5）：热榜API对接 + ChromaDB向量化
- Phase 3（Day 6-9）：10个Skill + Function Calling
- Phase 4（Day 10-12）：3个Agent编排联调
- Phase 5（Day 13-14）：任务接口 + 日志模块
- Phase 6（Day 15-16）：部署脚本 + Nginx配置

## API 接口


| 方法   | 路径                    | 说明         |
| ---- | --------------------- | ---------- |
| POST | /api/v1/auth/register | 用户注册       |
| POST | /api/v1/auth/login    | 用户登录       |
| GET  | /api/v1/auth/me       | 获取当前用户     |
| POST | /api/v1/auth/logout   | 登出         |
| GET  | /api/v1/users/me      | 用户详情       |
| PUT  | /api/v1/users/me      | 更新用户信息     |
| GET  | /health               | 健康检查       |
| GET  | /docs                 | Swagger 文档 |
