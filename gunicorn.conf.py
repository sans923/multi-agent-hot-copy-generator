"""
Gunicorn 生产环境配置
=====================
Gunicorn 是 Python 应用的 WSGI/ASGI 服务器
FastAPI 是 ASGI 框架，需要配合 uvicorn workers 使用

启动命令：
    gunicorn app.main:app -c gunicorn.conf.py

【为什么不直接用 uvicorn？】
uvicorn 单进程，只能利用一个 CPU 核心。
gunicorn 多进程管理器 + uvicorn workers：
  - gunicorn 负责进程管理（监控、重启、日志）
  - 每个 worker 是一个独立的 uvicorn 进程
  - 充分利用多核 CPU
"""

import os
import multiprocessing

# ====================================================
# 服务器绑定
# ====================================================
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
backlog = 2048  # 等待连接的队列长度

# ====================================================
# Worker 配置
# ====================================================
# 使用 uvicorn worker（FastAPI/Starlette ASGI框架必须用）
worker_class = "uvicorn.workers.UvicornWorker"

# Worker 数量：CPU核数 * 2 + 1（经验公式）
# 2核服务器：2 * 2 + 1 = 5，但内存只有2G，建议用 2-3
workers = int(os.getenv("GUNICORN_WORKERS", "2"))

# 每个 worker 的线程数（uvicorn worker 忽略此设置，保持默认）
threads = 1

# ====================================================
# 超时配置
# ====================================================
timeout = 180        # Worker 超时（Agent执行需要时间，设长一点）
keepalive = 5        # Keep-Alive 连接保持时间（秒）
graceful_timeout = 30  # 优雅关闭等待时间

# ====================================================
# 日志配置
# ====================================================
accesslog = "-"      # "-" 表示输出到 stdout（Docker环境标准）
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ====================================================
# 进程管理
# ====================================================
# Worker 处理 1000 个请求后重启（防内存泄漏）
max_requests = 1000
max_requests_jitter = 50  # 随机抖动，避免所有 worker 同时重启

preload_app = True  # 预加载应用（节省内存，但热重载失效）

# ====================================================
# Hooks（生命周期回调）
# ====================================================
def on_starting(server):
    server.log.info("Gunicorn 服务器启动中...")

def on_exit(server):
    server.log.info("Gunicorn 服务器正在关闭...")

def worker_init(worker):
    worker.log.info(f"Worker {worker.pid} 已启动")
