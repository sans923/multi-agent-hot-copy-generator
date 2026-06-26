#!/bin/bash
# ======================================================
# 火山引擎 ECS 一键部署脚本
# ======================================================
# 服务器配置：2核2G，Ubuntu 22.04，已设置 Swap
#
# 使用方法：
#   # 1. 上传项目到服务器
#   scp -r . root@你的服务器IP:/opt/copy-generator
#
#   # 2. SSH 登录服务器
#   ssh root@你的服务器IP
#
#   # 3. 执行部署脚本
#   cd /opt/copy-generator
#   chmod +x deploy.sh
#   ./deploy.sh
#
# 后续更新代码：
#   git pull
#   ./deploy.sh update

set -e  # 任何命令失败就退出（快速失败）

# ====================================================
# 颜色输出
# ====================================================
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'  # 恢复默认颜色

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ====================================================
# 配置变量
# ====================================================
APP_DIR="/opt/copy-generator"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="copy-generator"
PYTHON_VERSION="python3.11"

info "===== 多智能体热点爆款文案生成系统 部署脚本 ====="

# ====================================================
# Step 1: 系统依赖
# ====================================================
info "Step 1: 安装系统依赖..."

apt-get update -qq
apt-get install -y -qq \
    python3.11 \
    python3.11-venv \
    python3-pip \
    nginx \
    git \
    curl \
    supervisor  # 进程守护（比systemd更简单）

info "系统依赖安装完成"

# ====================================================
# Step 2: Python 虚拟环境
# ====================================================
info "Step 2: 配置 Python 虚拟环境..."

cd "$APP_DIR"

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON_VERSION -m venv "$VENV_DIR"
    info "虚拟环境创建完成"
fi

source "$VENV_DIR/bin/activate"

# 升级 pip
pip install --upgrade pip -q

# 安装依赖
info "安装 Python 依赖（可能需要几分钟）..."
pip install -r requirements.txt -q
pip install gunicorn -q  # 生产服务器

info "Python 依赖安装完成"

# ====================================================
# Step 3: 环境变量
# ====================================================
info "Step 3: 检查环境变量..."

if [ ! -f "$APP_DIR/.env" ]; then
    warning ".env 文件不存在，从模板创建..."
    cp .env.example .env
    warning "请编辑 $APP_DIR/.env 填入真实配置（尤其是 SECRET_KEY 和 DEEPSEEK_API_KEY）"
    warning "执行: nano $APP_DIR/.env"
    exit 1
fi

# 验证必填配置
source <(grep -E "^(SECRET_KEY|DEEPSEEK_API_KEY)=" .env)
if [ "$SECRET_KEY" = "dev-secret-key-change-this-before-production-use-32chars" ]; then
    error "请修改 .env 中的 SECRET_KEY！不能使用默认值"
fi
if [ -z "$DEEPSEEK_API_KEY" ] || [ "$DEEPSEEK_API_KEY" = "your-deepseek-api-key-here" ]; then
    error "请在 .env 中填入真实的 DEEPSEEK_API_KEY"
fi

info "环境变量检查通过"

# ====================================================
# Step 4: 创建数据目录
# ====================================================
info "Step 4: 创建数据目录..."

mkdir -p "$APP_DIR/data/chroma"
mkdir -p "$APP_DIR/logs"
mkdir -p "$APP_DIR/ssl"

info "数据目录创建完成"

# ====================================================
# Step 5: 配置 Supervisor（进程守护）
# ====================================================
info "Step 5: 配置 Supervisor..."

cat > /etc/supervisor/conf.d/copy-generator.conf << EOF
[program:copy-generator]
command=$VENV_DIR/bin/gunicorn app.main:app -c $APP_DIR/gunicorn.conf.py
directory=$APP_DIR
user=root
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$APP_DIR/logs/supervisor.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5
environment=PYTHONPATH="$APP_DIR"
EOF

supervisorctl reread
supervisorctl update

info "Supervisor 配置完成"

# ====================================================
# Step 6: 配置 Nginx
# ====================================================
info "Step 6: 配置 Nginx..."

cp "$APP_DIR/nginx.conf" /etc/nginx/nginx.conf

# 测试 Nginx 配置
nginx -t || error "Nginx 配置文件有语法错误"

systemctl restart nginx
systemctl enable nginx

info "Nginx 配置完成"

# ====================================================
# Step 7: 启动/重启服务
# ====================================================
info "Step 7: 启动服务..."

# 停止旧进程（如果有）
supervisorctl stop copy-generator 2>/dev/null || true

# 启动
supervisorctl start copy-generator

# 等待服务就绪
info "等待服务启动..."
sleep 5

# 健康检查
HEALTH_URL="http://localhost:8000/health"
if curl -sf "$HEALTH_URL" > /dev/null; then
    info "✅ 服务启动成功！"
    info "Swagger 文档: http://$(curl -s ifconfig.me)/docs"
else
    error "❌ 服务启动失败，查看日志: tail -f $APP_DIR/logs/supervisor.log"
fi

info "===== 部署完成 ====="
info ""
info "常用命令："
info "  查看服务状态:  supervisorctl status copy-generator"
info "  查看实时日志:  tail -f $APP_DIR/logs/supervisor.log"
info "  重启服务:      supervisorctl restart copy-generator"
info "  停止服务:      supervisorctl stop copy-generator"
