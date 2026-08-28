#!/bin/bash
# ============================================================
# 税务风险研判系统 - 统一启动脚本
# ============================================================
# 使用方式：
#   开发模式：  ./start.sh dev
#   生产模式：  ./start.sh prod
#   仅后端：    ./start.sh backend
#   仅前端：    ./start.sh frontend
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE=${1:-dev}

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================
# 检查依赖
# ============================================================
check_deps() {
  info "检查环境依赖..."

  # Python
  if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    error "未找到 Python，请先安装 Python 3.10+"
    exit 1
  fi
  PYTHON=$(command -v python3 || command -v python)
  info "Python: $($PYTHON --version)"

  # Node.js
  if ! command -v node &> /dev/null; then
    error "未找到 Node.js，请先安装 Node.js 18+"
    exit 1
  fi
  info "Node.js: $(node --version)"

  # pip
  if ! $PYTHON -m pip --version &> /dev/null; then
    error "未找到 pip，请先安装 pip"
    exit 1
  fi
}

# ============================================================
# 安装后端依赖
# ============================================================
install_backend() {
  info "安装后端 Python 依赖..."
  cd "$SCRIPT_DIR/backend"
  $PYTHON -m pip install -r requirements.txt -q
  cd "$SCRIPT_DIR"
}

# ============================================================
# 安装前端依赖
# ============================================================
install_frontend() {
  info "安装前端 Node.js 依赖..."
  cd "$SCRIPT_DIR"
  if [ ! -d "node_modules" ]; then
    npm install
  else
    info "node_modules 已存在，跳过安装"
  fi
}

# ============================================================
# 启动后端
# ============================================================
start_backend() {
  info "启动后端服务 (FastAPI + Uvicorn)..."
  cd "$SCRIPT_DIR/backend"

  # 检查 .env 文件
  if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
      warn ".env 文件不存在，复制 .env.example 作为默认配置"
      cp .env.example .env
    fi
  fi

  # 启动 uvicorn
  $PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
  BACKEND_PID=$!
  info "后端服务已启动 (PID: $BACKEND_PID) - http://localhost:8000"
  info "Swagger 文档: http://localhost:8000/docs"
  cd "$SCRIPT_DIR"
}

# ============================================================
# 启动前端（开发模式）
# ============================================================
start_frontend_dev() {
  info "启动前端开发服务器 (Vite)..."
  cd "$SCRIPT_DIR"
  npx vite --port 3000 &
  FRONTEND_PID=$!
  info "前端开发服务器已启动 (PID: $FRONTEND_PID) - http://localhost:3000"
}

# ============================================================
# 构建前端（生产模式）
# ============================================================
build_frontend() {
  info "构建前端生产版本..."
  cd "$SCRIPT_DIR"
  npx tsc -b && npx vite build
  info "前端构建完成 -> dist/"
}

# ============================================================
# 生产模式：前端静态文件由后端托管
# ============================================================
setup_prod_static() {
  info "配置后端托管前端静态文件..."
  DIST_DIR="$SCRIPT_DIR/dist"
  BACKEND_STATIC="$SCRIPT_DIR/backend/static"

  if [ ! -d "$DIST_DIR" ]; then
    error "前端构建产物 dist/ 不存在，请先构建前端"
    exit 1
  fi

  # 复制 dist 到 backend/static
  rm -rf "$BACKEND_STATIC"
  cp -r "$DIST_DIR" "$BACKEND_STATIC"

  info "静态文件已复制到 backend/static/"
  warn "注意：需要在后端 main.py 中添加静态文件托管路由"
  warn "或使用 nginx 反向代理分别托管前端和后端 API"
}

# ============================================================
# 主流程
# ============================================================
case "$MODE" in
  dev)
    info "========== 开发模式 =========="
    check_deps
    install_backend
    install_frontend
    start_backend
    sleep 2
    start_frontend_dev
    info ""
    info "=========================================="
    info "  前端: http://localhost:3000"
    info "  后端: http://localhost:8000"
    info "  Swagger: http://localhost:8000/docs"
    info "=========================================="
    info ""
    info "按 Ctrl+C 停止所有服务"
    wait
    ;;

  prod)
    info "========== 生产模式 =========="
    check_deps
    install_backend
    install_frontend
    build_frontend
    setup_prod_static
    info ""
    info "构建完成！启动后端服务..."
    start_backend
    info ""
    info "=========================================="
    info "  应用: http://localhost:8000"
    info "  Swagger: http://localhost:8000/docs"
    info "=========================================="
    info ""
    info "按 Ctrl+C 停止服务"
    wait
    ;;

  backend)
    info "========== 仅启动后端 =========="
    check_deps
    install_backend
    start_backend
    info ""
    info "后端服务: http://localhost:8000"
    info "Swagger: http://localhost:8000/docs"
    info "按 Ctrl+C 停止服务"
    wait
    ;;

  frontend)
    info "========== 仅启动前端 =========="
    check_deps
    install_frontend
    start_frontend_dev
    info ""
    info "前端开发服务器: http://localhost:3000"
    info "按 Ctrl+C 停止服务"
    wait
    ;;

  *)
    echo "用法: $0 {dev|prod|backend|frontend}"
    echo ""
    echo "  dev       开发模式（同时启动前后端）"
    echo "  prod      生产模式（构建前端 + 启动后端）"
    echo "  backend   仅启动后端"
    echo "  frontend  仅启动前端"
    exit 1
    ;;
esac
