#!/usr/bin/env bash
# 绿叶 AI 办公系统 — 开发与运维统一入口
#
# 日常只需记住本脚本（或仓库根目录 ./dev.sh）：
#
#   ./dev.sh local              # 本机 venv API + Vite（remote-dev 后推荐）
#   ./dev.sh local status       # 状态
#   ./dev.sh local restart      # 重启
#   ./dev.sh docker             # 全 Docker 热重载（compose dev-up）
#   ./dev.sh stop               # 停止 Docker 栈 + 本机进程
#   ./dev.sh remote-dev         # 生成本机 + 远程依赖 platform/.env
#
# 透传：./dev.sh stack …  |  ./dev.sh deploy …  |  ./dev.sh knowflow setup
#
set -euo pipefail
unset DOCKER_DEFAULT_PLATFORM DOCKER_PLATFORM

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/branding.sh
source "$SCRIPT_DIR/lib/branding.sh"
PLATFORM="$ROOT/platform"
RUN_DIR="$ROOT/.run"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[dev]${NC} $*"; }
warn()  { echo -e "${YELLOW}[dev]${NC} $*"; }
error() { echo -e "${RED}[dev]${NC} $*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { error "未找到命令: $1"; exit 1; }
}

stack_profiles() {
  echo "${DEV_STACK_PROFILES:-${ZHITAN_STACK_PROFILES:-${STACK_PROFILES:-knowflow speech}}}"
}

mode_stack() {
  require_cmd docker
  local -a pargs=()
  local profiles p
  profiles="$(stack_profiles)"
  for p in $profiles; do
    pargs+=(--profile "$p")
  done
  info "启动统一容器栈 profiles=${profiles}"
  bash "$SCRIPT_DIR/setup-stack-env.sh" 2>/dev/null || true
  bash "$SCRIPT_DIR/stack.sh" up "${pargs[@]}"
  print_urls docker
}

mode_stack_dev() {
  require_cmd docker
  info "全 Docker 开发模式（API 热重载，前端 Vite）"
  bash "$SCRIPT_DIR/setup-stack-env.sh" 2>/dev/null || true
  bash "$SCRIPT_DIR/stack.sh" dev-up "$@"
  print_urls docker
}

mode_stack_with_profile() {
  local profile="$1"
  DEV_STACK_PROFILES="$profile ${DEV_STACK_PROFILES:-${ZHITAN_STACK_PROFILES:-}}"
  mode_stack
}

print_urls() {
  local mode="${1:-local}"
  local port="${FRONTEND_PORT:-40005}"
  local app_name
  app_name="$(read_platform_app_name "$ROOT")"
  if [[ -f "$ROOT/.env" ]]; then
    port="$(grep -E '^FRONTEND_PORT=' "$ROOT/.env" | cut -d= -f2 | tr -d '\r' || echo "$port")"
  fi
  if [[ "$mode" == "docker" ]]; then
    cat <<EOF

${GREEN}=== ${app_name} v$(cat "$ROOT/VERSION" 2>/dev/null || echo '?')（Docker 开发）===${NC}

  Web:     http://127.0.0.1:${port}/ai/
  API:     http://127.0.0.1:18000  （容器 dev-up）
  日志:    ./dev.sh stack logs
  停止:    ./dev.sh stop

EOF
  else
    cat <<EOF

${GREEN}=== ${app_name} v$(cat "$ROOT/VERSION" 2>/dev/null || echo '?')（本机开发）===${NC}

  Web:     http://127.0.0.1:${port}/ai/
  API:     http://127.0.0.1:8000
  状态:    ./dev.sh local status
  停止:    ./dev.sh stop

EOF
  fi
}

dev_stop() {
  bash "$SCRIPT_DIR/stack.sh" down 2>/dev/null || true
  bash "$SCRIPT_DIR/local-dev.sh" stop 2>/dev/null || true
  info "已停止 Docker 栈与本机 dev 进程（API / Vite / Worker）"
}

dev_fix_local_env() {
  local ENV_FILE="$PLATFORM/.env"
  [[ -f "$ENV_FILE" ]] || cp "$PLATFORM/.env.example" "$ENV_FILE"
  info "platform/.env 已就绪，请确认 DATABASE_URL / KnowFlow 地址"
}

dev_remote_dev() {
  bash "$SCRIPT_DIR/setup-remote-dev-env.sh"
  info "已生成本机 remote-dev 用 platform/.env"
  info "验证远程: bash scripts/verify-remote-deps.sh"
  info "启动本机: ./dev.sh local"
  info "（全 Docker 开发: ./dev.sh docker）"
}

dev_knowflow_setup() {
  local TARGET="$PLATFORM/third_party/KnowFlow"
  local REPO="${KNOWFLOW_REPO:-https://github.com/knowflow-ai/KnowFlow.git}"
  local REF="${KNOWFLOW_REF:-main}"
  if [[ -d "$TARGET/.git" ]]; then
    git -C "$TARGET" pull --ff-only || true
  else
    mkdir -p "$(dirname "$TARGET")"
    git clone --depth 1 --branch "$REF" "$REPO" "$TARGET"
  fi
  [[ -f "$PLATFORM/knowflow.env" ]] || cp "$PLATFORM/knowflow.env.example" "$PLATFORM/knowflow.env"
  info "KnowFlow 源码就绪: $TARGET"
}

dev_knowflow_build() {
  local KF="$PLATFORM/third_party/KnowFlow"
  [[ -d "$KF" ]] || dev_knowflow_setup
  bash "$SCRIPT_DIR/download_knowflow_deps_light.sh" 2>/dev/null || true
  info "请使用 stack profile knowflow 或参阅 docs/zh/operations/deployment.md 构建镜像"
}

dev_speech_setup() {
  require_cmd docker
  local models_dir="${SPEECH_MODELS_DIR:-$ROOT/data/speech-models}"
  mkdir -p "$models_dir"
  export DATA_ROOT="${DATA_ROOT:-$ROOT/data}"
  info "模型目录: $models_dir"
  info "构建并启动 speech-api profile …"
  bash "$SCRIPT_DIR/stack.sh" build --profile speech
  bash "$SCRIPT_DIR/stack.sh" up --profile speech
  info "等待 speech-api（首次下载 ModelScope 模型，约 5–15 分钟）…"
  local i
  for i in $(seq 1 90); do
    if docker compose -p "${COMPOSE_PROJECT_NAME:-zhitan}" exec -T speech-api python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health')" 2>/dev/null; then
      info "speech-api 已就绪（容器内网 http://speech-api:8765）"
      return 0
    fi
    sleep 10
  done
  warn "speech-api 健康检查超时，请: ./dev.sh stack logs speech-api"
}

dev_local() {
  exec bash "$SCRIPT_DIR/local-dev.sh" "$@"
}

usage() {
  cat <<EOF
用法: ./dev.sh <命令> [参数]

开发（二选一）:
  local [start|status|stop|restart|logs]   本机 venv API :8000 + Vite :40005（推荐）
  docker                                   全 Docker 热重载（compose dev-up）
  up                                       生产式容器栈 up（非热重载）

环境与运维:
  stop                                     停止 Docker 栈 + 本机 dev 进程
  remote-dev                               生成 REMOTE_DEPS platform/.env
  env                                      检查/初始化 platform/.env
  stack …                                  透传 scripts/stack.sh（build / logs …）
  deploy …                                 透传 scripts/deploy.sh
  knowflow setup | build                   KnowFlow 源码
  speech setup                             构建并启动 speech profile

示例:
  REMOTE_HOST=服务器IP ./dev.sh remote-dev && ./dev.sh local
  ./dev.sh docker --profile knowflow --profile speech

文档: scripts/README.md
EOF
}

main() {
  mkdir -p "$RUN_DIR"
  local cmd="${1:-}"
  if [[ -z "$cmd" ]]; then
    usage
    exit 0
  fi
  shift || true
  case "$cmd" in
    local)
      dev_local "$@"
      ;;
    docker)
      mode_stack_dev "$@"
      ;;
    up)
      mode_stack "$@"
      ;;
    stop|down) dev_stop ;;
    env|fix-env) dev_fix_local_env ;;
    remote-dev) dev_remote_dev ;;
    stack) exec bash "$SCRIPT_DIR/stack.sh" "$@" ;;
    deploy) exec bash "$SCRIPT_DIR/deploy.sh" "$@" ;;
    knowflow)
      case "${1:-}" in
        setup) dev_knowflow_setup ;;
        build) dev_knowflow_build ;;
        *) error "用法: ./dev.sh knowflow setup|build"; exit 1 ;;
      esac
      ;;
    speech)
      case "${1:-}" in
        setup) dev_speech_setup ;;
        *) error "用法: ./dev.sh speech setup"; exit 1 ;;
      esac
      ;;
    -h|--help|help) usage ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
