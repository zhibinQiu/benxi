#!/usr/bin/env bash
# 文档 AI 平台启动脚本（本地优先）
# - 有 .venv / node_modules 时：pdf2zh、平台 API、Worker、前端在宿主机运行
# - 无本地环境时：回退 Docker 构建 api/worker/frontend
# - 基础设施（postgres / redis / minio）默认 Docker
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
FRONTEND="$ROOT/platform-frontend"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.local.yml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[start]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { error "未找到命令: $1"; exit 1; }
}

wait_url() {
  local url="$1" label="$2" retries="${3:-30}" interval="${4:-2}"
  local i
  for i in $(seq 1 "$retries"); do
    if curl -sf "$url" >/dev/null 2>&1; then
      info "$label 就绪"
      return 0
    fi
    sleep "$interval"
  done
  return 1
}

start_bg() {
  local name="$1" pid_file="$2" log_file="$3"
  shift 3
  mkdir -p "$(dirname "$pid_file")" "$LOG_DIR"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    info "$name 已在运行 (PID $(cat "$pid_file"))"
    return 0
  fi
  info "启动 $name ..."
  nohup "$@" >"$log_file" 2>&1 &
  echo $! >"$pid_file"
}

# --- 本地环境探测 ---

has_pdf2zh_local() {
  [[ -x "$ROOT/.venv/bin/pdf2zh_next" ]] || command -v pdf2zh_next >/dev/null 2>&1
}

pdf2zh_bin() {
  if [[ -x "$ROOT/.venv/bin/pdf2zh_next" ]]; then
    echo "$ROOT/.venv/bin/pdf2zh_next"
  else
    command -v pdf2zh_next
  fi
}

has_platform_venv() {
  [[ -x "$PLATFORM/.venv/bin/uvicorn" && -x "$PLATFORM/.venv/bin/celery" ]]
}

has_frontend_local() {
  [[ -d "$FRONTEND/node_modules" ]] && command -v npm >/dev/null 2>&1
}

# --- 各组件启动 ---

start_pdf2zh_api() {
  local bin
  bin="$(pdf2zh_bin)" || {
    error "未找到 pdf2zh_next。请在仓库根目录执行: pip install -e ."
    exit 1
  }
  if curl -sf "http://127.0.0.1:7861/api/health" >/dev/null 2>&1; then
    info "pdf2zh API 已在 7861 端口监听"
    return 0
  fi
  start_bg "pdf2zh API" "$RUN_DIR/pdf2zh-api.pid" "$LOG_DIR/pdf2zh-api.log" \
    "$bin" --api --api-port 7861
  wait_url "http://127.0.0.1:7861/api/health" "pdf2zh API" 60 2 \
    || { error "pdf2zh API 启动超时，日志: $LOG_DIR/pdf2zh-api.log"; exit 1; }
}

start_infra_docker() {
  require_cmd docker
  cd "$PLATFORM"
  [[ -f .env ]] || { info "复制 .env.example → .env"; cp .env.example .env; }
  info "启动 Docker 基础设施 (postgres, redis, minio) ..."
  $COMPOSE up -d postgres redis minio
  wait_url "http://127.0.0.1:9000/minio/health/live" "MinIO" 20 2 || true
}

start_platform_api_local() {
  if curl -sf "http://127.0.0.1:8000/docs" >/dev/null 2>&1; then
    info "平台 API 已在 8000 端口监听"
    return 0
  fi
  start_bg "平台 API" "$RUN_DIR/platform-api.pid" "$LOG_DIR/platform-api.log" \
    bash -c "cd '$PLATFORM' && source .venv/bin/activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
  wait_url "http://127.0.0.1:8000/docs" "平台 API" 30 2 \
    || warn "平台 API 可能仍在启动，日志: $LOG_DIR/platform-api.log"
}

start_platform_worker_local() {
  start_bg "Celery Worker" "$RUN_DIR/platform-worker.pid" "$LOG_DIR/platform-worker.log" \
    bash -c "cd '$PLATFORM' && source .venv/bin/activate && celery -A workers.celery_app worker --loglevel=info"
}

start_frontend_local() {
  if curl -sf "http://127.0.0.1:5174/" >/dev/null 2>&1; then
    info "平台前端已在 5174 端口监听"
    return 0
  fi
  start_bg "平台前端" "$RUN_DIR/platform-frontend.pid" "$LOG_DIR/platform-frontend.log" \
    bash -c "cd '$FRONTEND' && npm run dev -- --host 127.0.0.1 --port 5174"
  wait_url "http://127.0.0.1:5174/" "平台前端" 30 2 \
    || warn "平台前端可能仍在启动，日志: $LOG_DIR/platform-frontend.log"
}

start_platform_docker() {
  require_cmd docker
  cd "$PLATFORM"
  [[ -f .env ]] || { info "复制 .env.example → .env"; cp .env.example .env; }
  info "本地无 platform/.venv，使用 Docker 构建 api / worker / frontend ..."
  $COMPOSE --profile docker-app up -d --build api worker frontend
  wait_url "http://127.0.0.1:8000/docs" "平台 API" 30 2 \
    || warn "平台 API 可能仍在启动"
}

mode_local() {
  info "模式: 本地优先 (local)"
  start_infra_docker
  if has_pdf2zh_local; then
    start_pdf2zh_api
  else
    warn "未找到 pdf2zh 本地环境，跳过 pdf2zh API（翻译功能不可用）"
  fi
  if has_platform_venv; then
    start_platform_api_local
    start_platform_worker_local
  else
    warn "未找到 platform/.venv，回退 Docker 运行平台后端"
    start_platform_docker
    print_urls
    return
  fi
  if has_frontend_local; then
    start_frontend_local
  else
    warn "未找到 platform-frontend/node_modules，回退 Docker 前端"
    cd "$PLATFORM"
    $COMPOSE --profile docker-app up -d frontend
  fi
  print_urls
}

mode_docker() {
  info "模式: Docker 混合 (docker) — 宿主机 pdf2zh + Docker 平台"
  start_infra_docker
  if has_pdf2zh_local; then
    start_pdf2zh_api
  else
    error "docker 模式需要本地 pdf2zh_next (pip install -e .)"
    exit 1
  fi
  cd "$PLATFORM"
  $COMPOSE --profile docker-app up -d --build api worker frontend
  wait_url "http://127.0.0.1:8000/docs" "平台 API" 30 2 || true
  print_urls
}

mode_docker_full() {
  info "模式: 全 Docker (docker-full)"
  require_cmd docker
  cd "$PLATFORM"
  [[ -f .env ]] || cp .env.example .env
  docker compose --profile docker-full up -d --build
  print_urls
}

print_urls() {
  cat <<EOF

${GREEN}=== 文档 AI 平台已启动 ===${NC}

  平台前端:     http://127.0.0.1:5174
  平台 API:     http://127.0.0.1:8000  (Swagger: /docs)
  pdf2zh API:   http://127.0.0.1:7861
  MinIO 控制台: http://127.0.0.1:9001  (minioadmin / minioadmin)

  默认账号: admin / admin123

  停止: bash scripts/stop_platform.sh
  日志: ls $LOG_DIR/

EOF
}

usage() {
  cat <<EOF
用法: $0 [MODE]

MODE（默认 local）:
  local        本地优先：基础设施 Docker，其余用本机 .venv / npm（推荐）
  docker       混合：宿主机 pdf2zh + Docker 平台 api/worker/frontend
  docker-full  全部进 Docker（含 pdf2zh-api 镜像构建，首次较慢）

示例:
  bash scripts/start_platform.sh
  bash scripts/start_platform.sh local
EOF
}

main() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  case "${1:-local}" in
    up|start|local) mode_local ;;
    docker|hybrid)  mode_docker ;;
    docker-full)    mode_docker_full ;;
    -h|--help|help) usage ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
