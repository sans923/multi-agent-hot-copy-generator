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

## 技术栈

| 层次 | 技术 |
|------|------|
| Web 框架 | FastAPI |
| 大模型 | DeepSeek API |
| 向量数据库 | ChromaDB |
| 关系数据库 | SQLite（开发）/ MySQL（生产）|
| 热榜数据 | 韩小韩免费 API |
| 定时任务 | APScheduler |
| 部署 | 火山引擎 ECS + Nginx |

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
# 复制模板
copy .env.example .env

# 编辑 .env，填入：
# - SECRET_KEY（必须修改！）
# - DEEPSEEK_API_KEY（你的 API Key）
```

### 3. 启动服务

```bash
python run.py
```

访问 http://localhost:8000/docs 查看 API 文档

### 4. 运行测试

```bash
pip install pytest httpx
pytest tests/ -v
```

## 项目结构

```
multi-agent-hot-copy-generator/
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

- [x] Phase 1（Day 1-3）：项目初始化 + 数据库建表 + FastAPI框架 + 用户鉴权
- [ ] Phase 2（Day 4-5）：热榜API对接 + ChromaDB向量化
- [ ] Phase 3（Day 6-9）：10个Skill + Function Calling
- [ ] Phase 4（Day 10-12）：3个Agent编排联调
- [ ] Phase 5（Day 13-14）：任务接口 + 日志模块
- [ ] Phase 6（Day 15-16）：部署脚本 + Nginx配置

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/register | 用户注册 |
| POST | /api/v1/auth/login | 用户登录 |
| GET  | /api/v1/auth/me | 获取当前用户 |
| POST | /api/v1/auth/logout | 登出 |
| GET  | /api/v1/users/me | 用户详情 |
| PUT  | /api/v1/users/me | 更新用户信息 |
| GET  | /health | 健康检查 |
| GET  | /docs | Swagger 文档 |
