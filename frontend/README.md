# 前端（React + Vite）

多智能体热点爆款文案生成系统 Web 界面。

## 功能

- 登录 / 注册
- 工作台：任务列表
- 生成文案：提交需求、选平台、可选关联热榜
- 任务详情：自动轮询状态，展示终稿与复制
- 热榜：浏览 + 语义搜索

## 开发

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173

需同时启动后端（`python run.py`，端口 8000）。Vite 已将 `/api` 代理到后端。

## 生产构建

```bash
npm run build
```

产物在 `frontend/dist/`。可将该目录交由 Nginx 静态托管，并反向代理 `/api` 到 FastAPI。

## 环境变量

复制 `.env.example` 为 `.env`：

- `VITE_API_BASE`：生产环境填后端完整地址（如 `https://api.example.com`）；开发留空即可。

## 测试账号

可使用 `scripts/seed_users.py` 创建的账号，例如：

- `zhangsan@example.com` / 你的密码
- `lisi@example.com` / `Lisi123456`
