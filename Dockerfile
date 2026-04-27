# ======================================================
# 多阶段构建 Dockerfile
# ======================================================
# 为什么用多阶段构建（Multi-stage Build）？
# 阶段1（builder）：安装编译工具和依赖（镜像大）
# 阶段2（runtime）：只复制运行需要的文件（镜像小）
# 最终镜像不含编译工具，体积减少 50%+

# ======================================================
# 阶段 1：依赖安装
# ======================================================
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /app

# 安装系统依赖（编译某些Python包需要）
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件（利用 Docker 层缓存）
# 只有 requirements.txt 变化时才重新安装依赖，代码变化不触发重新安装
COPY requirements.txt .

# 安装 Python 依赖到独立目录
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ======================================================
# 阶段 2：运行时镜像
# ======================================================
FROM python:3.11-slim AS runtime

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 创建非 root 用户（安全最佳实践，不要用 root 运行服务）
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# 从 builder 阶段复制已安装的 Python 包
COPY --from=builder /install /usr/local

# 复制项目代码
COPY --chown=appuser:appuser . .

# 创建数据目录（SQLite数据库和ChromaDB存储）
RUN mkdir -p data/chroma logs && chown -R appuser:appuser data logs

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查（Docker 会定期调用，判断容器是否健康）
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令（生产环境用 gunicorn + uvicorn workers）
# -w 2：2个工作进程（2核2G服务器的推荐值）
# --timeout 120：任务执行可能较慢，超时设置长一点
CMD ["gunicorn", "app.main:app", \
     "-w", "2", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
