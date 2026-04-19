"""
项目启动入口
============
两种启动方式：

方式1（开发环境，推荐）：
    python run.py
    特点：代码改动后自动重载（reload=True），不需要手动重启

方式2（生产环境）：
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
    特点：多进程，性能更好
    注意：生产环境不要开 reload

方式3（使用 gunicorn + uvicorn，最佳生产配置）：
    gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
"""

import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",       # 模块路径:应用变量名
        host="0.0.0.0",       # 监听所有网络接口（0.0.0.0 才能被外部访问）
        port=settings.PORT,   # 端口号，默认 8000
        reload=settings.DEBUG, # 开发模式下热重载
        log_level="info",
    )
