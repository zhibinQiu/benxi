#!/usr/bin/env bash
# amd64 服务器一键部署（全 Docker 生产栈）
#
# 用法:
#   bash scripts/deploy_amd64.sh full          # 并行：核心 + KnowFlow + 语音
#   bash scripts/deploy_amd64.sh full --wait   # 同上并等待 pdf2zh 健康检查
#   bash scripts/deploy_amd64.sh down
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
DEPLOY_TARGET="${DEPLOY_TARGET:-$PLATFORM/deploy.target.amd64}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
if [[ "${DEPLOY_USE_MIRROR:-auto}" == 1 ]] || [[ "${DEPLOY_USE_MIRROR:-auto}" == auto ]]; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.mirror.yml"
fi
COMPOSE="docker compose $COMPOSE_FILES"
SPEECH_COMPOSE="docker compose -f docker-compose.speech.yml -f docker-compose.speech.prod.yml"
export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/amd64}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-zhitanai}"
DEPLOY_PARALLEL="${DEPLOY_PARALLEL:-1}"
DEPLOY_WAIT_PDF2ZH="${DEPLOY_WAIT_PDF2ZH:-0}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} $*"; }
error() { echo -e "${RED}[deploy]${NC} $*" >&2; }

load_deploy_target() {
  if [[ -f "$DEPLOY_TARGET" ]]; then
    # shellcheck disable=SC1090
    set -a && source "$DEPLOY_TARGET" && set +a
  fi
}
load_deploy_target

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { error "未找到: $1"; exit 1; }
}

detect_host() {
  local ip="${DEPLOY_HOST:-}"
  [[ -n "$ip" ]] && { echo "$ip"; return; }
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')" || true
  [[ -z "$ip" ]] && ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="src") print $(i+1)}')" || true
  [[ -z "$ip" ]] && ip="127.0.0.1"
  echo "$ip"
}

sync_env_from_local() {
  cd "$PLATFORM"
  if [[ -f .env.docker ]]; then
    info "应用 platform/.env.docker → .env（amd64）"
    cp -f .env.docker .env
  else
    info "生成 amd64 配置 ..."
    bash "$ROOT/scripts/sync_deploy_env.sh"
    cp -f .env.docker .env
  fi
  if [[ -f knowflow.env.docker ]]; then
    cp -f knowflow.env.docker knowflow.env
  fi
}

ensure_platform_network() {
  # 必须由 compose 创建（带正确 label），勿手建 platform_default
  cd "$PLATFORM"
  $COMPOSE up -d postgres redis minio 2>/dev/null || true
}

wait_pdf2zh_optional() {
  [[ "$DEPLOY_WAIT_PDF2ZH" == 1 ]] || return 0
  info "等待 pdf2zh-api 健康检查..."
  local i
  for i in $(seq 1 90); do
    curl -sf "http://127.0.0.1:7861/api/health" >/dev/null 2>&1 && return 0
    sleep 5
  done
  warn "pdf2zh-api 可能仍在 warmup: cd platform && $COMPOSE logs -f pdf2zh-api"
}

warn_deepseek_key() {
  if [[ -f "$PLATFORM/.env" ]] && ! grep -qE '^DEEPSEEK_API_KEY=.+.' "$PLATFORM/.env" 2>/dev/null; then
    warn "未配置 DEEPSEEK_API_KEY，录音「总结」不可用（转写仍可用）"
  fi
}

# --- KnowFlow（后台任务）---
_job_knowflow() {
  cd "$PLATFORM"
  bash "$ROOT/scripts/setup_knowflow.sh"
  [[ -f knowflow.env ]] || cp -f knowflow.env.docker knowflow.env 2>/dev/null \
    || cp -f knowflow.env.example knowflow.env
  set -a
  # shellcheck disable=SC1091
  source knowflow.env
  set +a
  export COMPOSE_PROFILES="${COMPOSE_PROFILES:-elasticsearch}"
  local -a kf_profile_args=()
  local p
  IFS=',' read -ra _kf_prof <<< "${COMPOSE_PROFILES}"
  for p in "${_kf_prof[@]}"; do
    p="${p// /}"
    [[ -n "$p" ]] && kf_profile_args+=(--profile "$p")
  done
  local -a kf_compose=(-f docker-compose.knowflow.amd64.yml)
  if [[ "${DEPLOY_USE_MIRROR:-1}" == 1 ]] || [[ "${DEPLOY_USE_MIRROR:-auto}" == auto ]]; then
    kf_compose+=(-f docker-compose.knowflow.mirror.yml)
    info "[并行] KnowFlow：使用 docker.1ms.run 镜像源"
  fi
  info "[并行] KnowFlow：拉取镜像并启动（profiles=${COMPOSE_PROFILES}）..."
  docker compose -p knowflow "${kf_profile_args[@]}" \
    "${kf_compose[@]}" \
    --env-file knowflow.env \
    pull 2>/dev/null || true
  docker compose -p knowflow "${kf_profile_args[@]}" \
    "${kf_compose[@]}" \
    --env-file knowflow.env \
    up -d
  info "[并行] KnowFlow 栈已提交启动"
}

# --- 语音（后台任务）---
_job_speech() {
  cd "$PLATFORM"
  SPEECH_MODELS="${SPEECH_MODELS_DIR:-$ROOT/.run/speech-models}"
  mkdir -p "$SPEECH_MODELS"
  export SPEECH_MODELS_DIR="$SPEECH_MODELS"
  info "[并行] 语音：构建并启动 speech-api ..."
  $SPEECH_COMPOSE build --parallel
  $SPEECH_COMPOSE up -d
  info "[并行] 语音栈已提交启动"
}

_job_core_build_up() {
  cd "$PLATFORM"
  info "[并行] 核心：并行构建镜像 ..."
  $COMPOSE build --parallel
  info "[并行] 核心：启动应用容器 ..."
  $COMPOSE up -d
  info "[并行] 核心栈已启动"
}

_job_core() {
  cd "$PLATFORM"
  $COMPOSE up -d postgres redis minio
  _job_core_build_up
}

start_core() {
  require_cmd docker
  sync_env_from_local
  ensure_platform_network
  cd "$PLATFORM"
  if [[ "$DEPLOY_PARALLEL" == 1 ]]; then
    _job_core
  else
    info "构建并启动核心栈（串行）..."
    $COMPOSE up -d --build
  fi
  wait_pdf2zh_optional
}

start_knowflow() {
  ensure_platform_network
  _job_knowflow
  cd "$PLATFORM"
  $COMPOSE up -d api worker
}

start_speech() {
  ensure_platform_network
  _job_speech
  warn_deepseek_key
}

# full：三路并行（KnowFlow 拉镜像 | 核心 build | 语音 build）
start_full_parallel() {
  require_cmd docker
  sync_env_from_local
  mkdir -p "$ROOT/.run"
  cd "$PLATFORM"

  info "=== 并行部署：先启动基础设施网络 ==="
  $COMPOSE up -d postgres redis minio

  info "=== 并行：核心构建 | KnowFlow | 语音 ==="
  local pids=()

  (_job_knowflow) >"$ROOT/.run/deploy-knowflow.log" 2>&1 &
  pids+=($!)

  (_job_speech) >"$ROOT/.run/deploy-speech.log" 2>&1 &
  pids+=($!)

  (_job_core_build_up) >"$ROOT/.run/deploy-core.log" 2>&1 &
  pids+=($!)

  local p ec=0
  for p in "${pids[@]}"; do
    wait "$p" || ec=1
  done

  cd "$PLATFORM"
  $COMPOSE up -d api worker

  if [[ "$ec" -ne 0 ]]; then
    warn "部分并行任务失败，见 .run/deploy-*.log"
  fi

  wait_pdf2zh_optional
  warn_deepseek_key
}

read_frontend_port() {
  local port="${FRONTEND_PORT:-40005}"
  local f
  for f in "$PLATFORM/.env.docker" "$PLATFORM/.env"; do
    if [[ -f "$f" ]]; then
      port="$(grep -E '^FRONTEND_PORT=' "$f" 2>/dev/null | cut -d= -f2)" || port="${FRONTEND_PORT:-40005}"
      [[ -n "$port" ]] && break
    fi
  done
  [[ -z "$port" ]] && port=40005
  echo "$port"
}

print_urls() {
  local host port path_hint
  host="$(detect_host)"
  path_hint="${DEPLOY_PATH:-$ROOT}"
  port="$(read_frontend_port)"
  cat <<EOF

${GREEN}=== 部署已提交（amd64）===${NC}
  目录:         ${path_hint}
  并行日志:     .run/deploy-core.log / deploy-knowflow.log / deploy-speech.log

  平台 Web:     http://${host}:${port}/ai/
  平台 API:     http://${host}:8000/docs
  pdf2zh API:   http://${host}:7861
  MinIO:        http://${host}:9001
  RAGFlow:      http://${host}:9380
  KnowFlow API: http://${host}:5001
  语音 API:     http://${host}:8765

  查看总日志:   tail -f .run/deploy.log
  停止:         bash scripts/deploy_amd64.sh down

EOF
}

cmd_down() {
  cd "$PLATFORM"
  $COMPOSE down
  docker compose -p knowflow -f docker-compose.knowflow.amd64.yml down 2>/dev/null || true
  $SPEECH_COMPOSE down 2>/dev/null || true
  info "已停止"
}

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  echo "  --wait    等待 pdf2zh 健康检查完成后再退出"
}

main() {
  local mode="${1:-core}"
  shift || true
  for arg in "$@"; do
    case "$arg" in
      --wait) DEPLOY_WAIT_PDF2ZH=1 ;;
      --serial) DEPLOY_PARALLEL=0 ;;
      -h|--help) usage; exit 0 ;;
    esac
  done

  case "$mode" in
    core|"")
      start_core
      print_urls
      ;;
    knowflow)
      start_core
      start_knowflow
      print_urls
      ;;
    speech)
      start_core
      start_speech
      print_urls
      ;;
    full)
      if [[ "$DEPLOY_PARALLEL" == 1 ]]; then
        start_full_parallel
      else
        start_core
        start_knowflow
        start_speech
      fi
      print_urls
      info "KnowFlow ES/MySQL、FunASR 模型可能仍在初始化，请用 docker ps / logs 查看"
      ;;
    down|stop)
      cmd_down
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
