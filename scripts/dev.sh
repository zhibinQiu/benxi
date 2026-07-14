#!/usr/bin/env bash
# 企业 AI 知识库平台 — 开发与运维统一入口
#
# 日常只需记住本脚本（或仓库根目录 ./dev.sh）：
#
#   ./dev.sh local              # 本机 venv API + Vite（remote-dev 后推荐）
#   ./dev.sh local status       # 状态
#   ./dev.sh local restart      # 重启
#   ./dev.sh docker             # 全 Docker 热重载（compose dev-up）
#   ./dev.sh stop               # 停止 Docker 栈 + 本机进程
#   ./dev.sh remote-dev         # 生成本机 + 远程依赖 backend/.env
#
#   ./dev.sh sync [--frontend|--all|--no-restart-api]  同步代码到服务器（默认重启 API/Worker）
#   ./dev.sh sync-frp-uninstall                 卸载服务器 frps
#
set -euo pipefail
unset DOCKER_DEFAULT_PLATFORM DOCKER_PLATFORM

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/branding.sh
source "$SCRIPT_DIR/lib/branding.sh"
PLATFORM="$ROOT/backend"
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
  echo "${DEV_STACK_PROFILES:-${BENXI_STACK_PROFILES:-${STACK_PROFILES:-knowflow speech}}}"
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
  DEV_STACK_PROFILES="$profile ${DEV_STACK_PROFILES:-${BENXI_STACK_PROFILES:-}}"
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
  bash "$SCRIPT_DIR/dev-frpc.sh" stop 2>/dev/null || true
  info "已停止 Docker 栈与本机 dev 进程（API / Vite / Worker / frpc）"
}

dev_fix_local_env() {
  local ENV_FILE="$PLATFORM/.env"
  [[ -f "$ENV_FILE" ]] || cp "$PLATFORM/.env.example" "$ENV_FILE"
  info "backend/.env 已就绪，请确认 DATABASE_URL / KnowFlow 地址"
}

dev_remote_dev() {
  bash "$SCRIPT_DIR/setup-env.sh" remote-dev
  info "已生成本机 remote-dev 用 backend/.env"
  info "验证远程: bash scripts/verify-remote-deps.sh"
  info "启动本机: ./dev.sh local"
  info "（全 Docker 开发: ./dev.sh docker）"
}

dev_knowflow_setup() {
  local TARGET="$ROOT/third_party/knowflow"
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
  local KF="$ROOT/third_party/knowflow"
  [[ -d "$KF" ]] || dev_knowflow_setup
  bash "$SCRIPT_DIR/download_knowflow_deps_light.sh" 2>/dev/null || true
  info "请使用 stack profile knowflow 或参阅 docs/zh/operations/deployment.md 构建镜像"
}

dev_speech_setup() {
  require_cmd docker
  local models_dir="${SPEECH_MODELS_DIR:-$ROOT/third_party/data/speech-models}"
  mkdir -p "$models_dir"
  export DATA_ROOT="${DATA_ROOT:-$ROOT/data}"
  info "模型目录: $models_dir"
  info "构建并启动 speech-api profile …"
  bash "$SCRIPT_DIR/stack.sh" build --profile speech
  bash "$SCRIPT_DIR/stack.sh" up --profile speech
  info "等待 speech-api（首次下载 ModelScope 模型，约 5–15 分钟）…"
  local i
  for i in $(seq 1 90); do
    if docker compose -p "${COMPOSE_PROJECT_NAME:-benxi}" exec -T speech-api python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health')" 2>/dev/null; then
      info "speech-api 已就绪（容器内网 http://speech-api:8765）"
      return 0
    fi
    sleep 10
  done
  warn "speech-api 健康检查超时，请: ./dev.sh stack logs speech-api"
}

dev_speech_local() {
  exec bash "$SCRIPT_DIR/start-speech-local.sh"
}

dev_docs() {
  case "${1:-}" in
    local)
      exec bash "$SCRIPT_DIR/start-docs.sh"
      ;;
    stop)
      if [[ -f "$RUN_DIR/docs.pid" ]] && kill -0 "$(cat "$RUN_DIR/docs.pid")" 2>/dev/null; then
        kill "$(cat "$RUN_DIR/docs.pid")" 2>/dev/null || true
        rm -f "$RUN_DIR/docs.pid"
        info "已停止本机文档站"
      fi
      docker compose -p "${COMPOSE_PROJECT_NAME:-benxi}" --profile docs stop docs 2>/dev/null || true
      ;;
    *)
      require_cmd docker
      local port="${DOCS_PORT:-40100}"
      if [[ -f "$ROOT/.env" ]]; then
        port="$(grep -E '^DOCS_PORT=' "$ROOT/.env" | cut -d= -f2 | tr -d '\r' || echo "$port")"
      fi
      info "启动文档站容器（profile docs）…"
      bash "$SCRIPT_DIR/setup-stack-env.sh" 2>/dev/null || true
      bash "$SCRIPT_DIR/stack.sh" up --profile docs --build docs
      cat <<EOF

${GREEN}=== 系统文档站 ===${NC}

  文档:    http://127.0.0.1:${port}/
  日志:    ./dev.sh stack logs docs
  停止:    ./dev.sh docs stop

EOF
      ;;
  esac
}

dev_local() {
  exec bash "$SCRIPT_DIR/local-dev.sh" "$@"
}

dev_frp() {
  case "${1:-}" in
    install-server)
      shift || true
      exec bash "$SCRIPT_DIR/frp-server-install.sh" "$@"
      ;;
    *)
      exec bash "$SCRIPT_DIR/dev-frpc.sh" "$@"
      ;;
  esac
}

usage() {
  cat <<EOF
用法: ./dev.sh <命令> [参数]

开发（二选一）:
  local [start|status|stop|restart|logs]   本机 venv API :8000 + Vite :40005（推荐）
  docker                                   全 Docker 热重载（compose dev-up）
  up                                       生产式容器栈 up（非热重载）

服务器管理（全新）:
  server restart                           构建+重启服务器所有服务（含编译）
  server restart --base                    只重启基础服务（postgres/redis/minio 等）
  server restart --service <名称>          只重启指定服务
  server status                            查看服务器服务状态（彩色指示灯）
  server build                             在服务器构建镜像
  server logs [服务名]                     查看服务器日志
  server pull                              拉取最新代码并重启（无编译）

总体状态:
  status                                   同时检查本地和服务器服务状态

环境与运维:
  stop                                     停止 Docker 栈 + 本机 dev 进程
  remote-dev                               生成 REMOTE_DEPS backend/.env
  sync [--frontend|--all|--browser]                    同步代码到服务器并重启 API/Worker
  sync --with-data                         同步代码 + 服务器端数据备份（stack.sh backup，不拉到本地）
  sync --backup                            仅服务器端数据备份（不同步代码）
  sync-frp-uninstall                       卸载服务器 frps
  db migrate to-local|to-remote          平台 PostgreSQL 迁移
  env remote-dev|local-db                  生成 backend/.env
  fix-env                                  检查/初始化 backend/.env 模板
  stack …                                  透传 scripts/stack.sh（build / logs …）
  deploy …                                 透传 scripts/deploy.sh
  knowflow setup | build                   KnowFlow 源码
  speech setup | local                     speech-api（Docker profile / 宿主机）
  docs [local|stop]                          MkDocs 文档站（Docker :40100 / 本机 local）
  browser setup [--docker|--server]                 Playwright Chromium（浏览器 RPA）
  data-dir migrate                          迁移 third_party/data 到项目根目录 data

示例:
  REMOTE_HOST=服务器IP ./dev.sh remote-dev && ./dev.sh local
  ./dev.sh server restart                     # 从本机管理服务器
  ./dev.sh server status                      # 查看服务器服务状态
  ./dev.sh status                             # 同时查看本地+服务器状态
  ./dev.sh sync --with-data                   # 同步代码 + 服务器端数据备份
  ./dev.sh backup                             # 仅服务器端数据备份（不同步代码）
  ./dev.sh data-dir migrate                   # 迁移数据目录

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
    server)
      exec bash "$SCRIPT_DIR/server.sh" "$@"
      ;;
    status)
      bash "$SCRIPT_DIR/local-dev.sh" status
      echo ""
      bash "$SCRIPT_DIR/server.sh" status
      ;;
    docker)
      mode_stack_dev "$@"
      ;;
    up)
      mode_stack "$@"
      ;;
    stop|down) dev_stop ;;
    fix-env) dev_fix_local_env ;;
    remote-dev) dev_remote_dev ;;
    frp) dev_frp "$@" ;;
    sync)
      exec bash "$SCRIPT_DIR/server-sync.sh" "$@"
      ;;
    data-sync|backup)
      exec bash "$SCRIPT_DIR/server-sync.sh" --backup
      ;;
    data-dir)
      case "${1:-}" in
        migrate)
          exec bash "$SCRIPT_DIR/migrate-data-dir.sh"
          ;;
        *)
          error "用法: ./dev.sh data-dir migrate"
          exit 1
          ;;
      esac
      ;;
    sync-frp-uninstall)
      exec bash "$SCRIPT_DIR/server-uninstall-frp.sh" "$@"
      ;;
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
        local) dev_speech_local ;;
        *) error "用法: ./dev.sh speech setup|local"; exit 1 ;;
      esac
      ;;
    docs) dev_docs "$@" ;;
    browser)
      shift || true
      case "${1:-setup}" in
        setup)
          shift || true
          exec bash "$SCRIPT_DIR/setup-browser-rpa.sh" "${1:-local}"
          ;;
        *)
          error "用法: ./dev.sh browser setup [local|--docker|--server]"
          exit 1
          ;;
      esac
      ;;
    db)
      case "${1:-}" in
        migrate)
          shift || true
          exec bash "$SCRIPT_DIR/migrate-postgres.sh" "$@"
          ;;
        *)
          error "用法: ./dev.sh db migrate to-local|to-remote"
          exit 1
          ;;
      esac
      ;;
    env)
      case "${1:-}" in
        remote-dev|local-db)
          exec bash "$SCRIPT_DIR/setup-env.sh" "$@"
          ;;
        *)
          dev_fix_local_env
          ;;
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
