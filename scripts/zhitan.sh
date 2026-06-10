#!/usr/bin/env bash
# 智碳平台 — 开发与运维统一入口（薄包装，编排见 scripts/stack.sh）
#
#   bash scripts/zhitan.sh              # 启动统一栈（默认 profile: knowflow speech）
#   bash scripts/zhitan.sh dev          # 开发模式（热重载 + 源码挂载）
#   bash scripts/zhitan.sh stop         # 停止栈
#   bash scripts/zhitan.sh stack …      # 透传 stack.sh（build / save / logs …）
#   bash scripts/zhitan.sh env            # 修正 platform/.env 为本机地址
#   bash scripts/zhitan.sh remote-dev     # 生成本机 + 远程依赖的 platform/.env
#   bash scripts/zhitan.sh knowflow setup|build
#   bash scripts/zhitan.sh deploy stack push
#
set -euo pipefail
unset DOCKER_DEFAULT_PLATFORM DOCKER_PLATFORM

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM="$ROOT/platform"
RUN_DIR="$ROOT/.run"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[zhitan]${NC} $*"; }
warn()  { echo -e "${YELLOW}[zhitan]${NC} $*"; }
error() { echo -e "${RED}[zhitan]${NC} $*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { error "未找到命令: $1"; exit 1; }
}

deprecated_mode() {
  error "$1 已废弃，请使用: bash scripts/zhitan.sh dev  或  bash scripts/stack.sh dev-up"
  exit 1
}

stack_profiles() {
  echo "${ZHITAN_STACK_PROFILES:-${STACK_PROFILES:-knowflow speech}}"
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
  print_urls
}

mode_stack_dev() {
  require_cmd docker
  info "开发模式: stack dev-up（API 热重载，前端 Vite）"
  bash "$SCRIPT_DIR/setup-stack-env.sh" 2>/dev/null || true
  bash "$SCRIPT_DIR/stack.sh" dev-up "$@"
  print_urls
}

mode_stack_with_profile() {
  local profile="$1"
  ZHITAN_STACK_PROFILES="$profile ${ZHITAN_STACK_PROFILES:-}"
  mode_stack
}

print_urls() {
  local port="${FRONTEND_PORT:-40005}"
  if [[ -f "$ROOT/.env" ]]; then
    port="$(grep -E '^FRONTEND_PORT=' "$ROOT/.env" | cut -d= -f2 | tr -d '\r' || echo "$port")"
  fi
  cat <<EOF

${GREEN}=== 智碳平台 v$(cat "$ROOT/VERSION" 2>/dev/null || echo '?') ===${NC}

  Web:     http://127.0.0.1:${port}/ai/
  API dev: http://127.0.0.1:18000  （dev-up 时）
  日志:    bash scripts/stack.sh logs
  停止:    bash scripts/zhitan.sh stop

EOF
}

zhitan_stop() {
  bash "$SCRIPT_DIR/stack.sh" down 2>/dev/null || true
  info "已停止"
}

zhitan_fix_local_env() {
  local ENV_FILE="$PLATFORM/.env"
  [[ -f "$ENV_FILE" ]] || cp "$PLATFORM/.env.example" "$ENV_FILE"
  info "platform/.env 已就绪，请确认 DATABASE_URL / KnowFlow 地址为本机或 remote-dev"
}

zhitan_remote_dev() {
  bash "$SCRIPT_DIR/setup-remote-dev-env.sh"
  info "已生成本机 remote-dev 用 platform/.env，请执行: bash scripts/zhitan.sh dev"
}

zhitan_knowflow_setup() {
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

zhitan_knowflow_build() {
  local KF="$PLATFORM/third_party/KnowFlow"
  [[ -d "$KF" ]] || zhitan_knowflow_setup
  bash "$SCRIPT_DIR/download_knowflow_deps_light.sh" 2>/dev/null || true
  info "请使用 stack profile knowflow 或参阅 docs/zh/operations/deployment.md 构建镜像"
}

usage() {
  cat <<EOF
用法: bash scripts/zhitan.sh <命令> [参数]

命令:
  start [stack|dev|knowflow|speech]   默认 stack；dev=热重载
  dev                               同 start dev
  stop                              stack.sh down
  stack …                           透传 scripts/stack.sh
  env                               本机 platform/.env
  remote-dev                        本机前端 + 远程依赖（见 setup-remote-dev-env.sh）
  knowflow setup | build            KnowFlow 源码
  deploy stack push                 远程镜像部署

文档: docs/zh/operations/README.md
EOF
}

main() {
  mkdir -p "$RUN_DIR"
  local cmd="${1:-start}"
  shift || true
  case "$cmd" in
    start|up)
      case "${1:-stack}" in
        stack|"") mode_stack ;;
        dev) shift; mode_stack_dev "$@" ;;
        knowflow) mode_stack_with_profile knowflow ;;
        speech) mode_stack_with_profile speech ;;
        legacy|local|docker|hybrid|docker-full) deprecated_mode "$1" ;;
        *) usage; exit 1 ;;
      esac
      ;;
    dev) mode_stack_dev "$@" ;;
    stack) exec bash "$SCRIPT_DIR/stack.sh" "$@" ;;
    stop) zhitan_stop ;;
    env|fix-env) zhitan_fix_local_env ;;
    remote-dev) zhitan_remote_dev ;;
    knowflow)
      case "${1:-}" in
        setup) zhitan_knowflow_setup ;;
        build) zhitan_knowflow_build ;;
        *) error "用法: zhitan.sh knowflow setup|build"; exit 1 ;;
      esac
      ;;
    deploy) exec bash "$SCRIPT_DIR/deploy.sh" "$@" ;;
    -h|--help|help) usage ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
