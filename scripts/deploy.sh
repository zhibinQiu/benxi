#!/usr/bin/env bash
# AI 办公系统 — 生产部署：镜像 save/load 推送到远程（不 rsync 源码）
#
# 配置: platform/deploy.target（由 deploy.target.example 复制）
#
# 用法:
#   bash scripts/stack.sh build --profile knowflow --profile speech
#   bash scripts/stack.sh save
#   bash scripts/deploy.sh stack push      # 推送到 deploy.target 中的服务器
#   bash scripts/deploy.sh local stack     # 目标机本地 load + up
#
# 已废弃: deploy.sh app/full/core/knowflow/speech/down（请用 stack.sh）
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
# shellcheck source=lib/version.sh
source "$ROOT/scripts/lib/version.sh"
# shellcheck source=lib/branding.sh
source "$ROOT/scripts/lib/branding.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

# --- 运行模式 ---
RUN_LOCAL=0
DO_PUSH=1
DO_DEPLOY=1
DO_STATUS=0
DEPLOY_MODE="app"
RSYNC_DELETE="${DEPLOY_RSYNC_DELETE:-0}"

DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST=""
DEPLOY_PATH=""
DEPLOY_ARCH="${DEPLOY_ARCH:-auto}"
DEPLOY_TARGET="${DEPLOY_TARGET:-}"
TARGET_FILE=""

COMPOSE_FILES=""
COMPOSE=""
SPEECH_COMPOSE="docker compose -f docker-compose.speech.yml -f docker-compose.speech.prod.yml"
KF_COMPOSE_FILE=""
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-zhitanai}"
DEPLOY_PARALLEL="${DEPLOY_PARALLEL:-1}"
DEPLOY_WAIT_PDF2ZH="${DEPLOY_WAIT_PDF2ZH:-0}"

# ---------------------------------------------------------------------------
resolve_target_file() {
  if [[ -n "$DEPLOY_TARGET" && -f "$DEPLOY_TARGET" ]]; then
    TARGET_FILE="$DEPLOY_TARGET"
    return
  fi
  for f in "$PLATFORM/deploy.target"; do
    if [[ -f "$f" ]]; then
      TARGET_FILE="$f"
      DEPLOY_TARGET="$f"
      return
    fi
  done
  TARGET_FILE=""
}

load_target() {
  resolve_target_file
  [[ -n "$TARGET_FILE" ]] || return 1
  # shellcheck disable=SC1090
  set -a && source "$TARGET_FILE" && set +a
  DEPLOY_USER="${DEPLOY_USER:-root}"
  DEPLOY_ARCH="${DEPLOY_ARCH:-auto}"
  [[ -n "${DEPLOY_HOST:-}" && -n "${DEPLOY_PATH:-}" ]] \
    || { error "deploy.target 需设置 DEPLOY_HOST 与 DEPLOY_PATH"; exit 1; }
}

_tolower() { printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'; }

normalize_arch() {
  local raw
  raw="$(_tolower "${1:-}")"
  case "$raw" in
    x86_64|amd64) echo amd64 ;;
    aarch64|arm64) echo arm64 ;;
    auto|'')
      case "$(uname -m)" in
        x86_64) echo amd64 ;;
        aarch64|arm64) echo arm64 ;;
        *) error "不支持的架构: $(uname -m)"; exit 1 ;;
      esac
      ;;
    *) error "未知 DEPLOY_ARCH=${1:-}（可用 auto / amd64 / arm64）"; exit 1 ;;
  esac
}

detect_remote_arch() {
  local raw
  raw="$(_tolower "${DEPLOY_ARCH:-auto}")"
  if [[ "$raw" != auto ]]; then
    normalize_arch "$raw"
    return
  fi
  local uname_m
  uname_m="$(ssh -o BatchMode=yes -o ConnectTimeout=10 \
    "${DEPLOY_USER}@${DEPLOY_HOST}" 'uname -m' 2>/dev/null)" \
    || { error "无法 SSH 检测远程架构，请在 deploy.target 设置 DEPLOY_ARCH=amd64|arm64"; exit 1; }
  info "远程 uname -m → ${uname_m}"
  normalize_arch "$uname_m"
}

configure_for_arch() {
  local arch="$1"
  DEPLOY_ARCH="$arch"
  case "$arch" in
    amd64)
      COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
      KF_COMPOSE_FILE="docker-compose.knowflow.amd64.yml"
      export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/amd64}"
      ;;
    arm64)
      COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.arm64.yml"
      KF_COMPOSE_FILE="docker-compose.knowflow.yml"
      export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/arm64}"
      ;;
    *) error "内部错误: arch=$arch"; exit 1 ;;
  esac
  if [[ "${DEPLOY_USE_MIRROR:-1}" == 1 ]] || [[ "${DEPLOY_USE_MIRROR:-auto}" == auto ]]; then
    COMPOSE_FILES+=" -f docker-compose.mirror.yml"
  fi
  COMPOSE="docker compose ${COMPOSE_FILES}"
  info "目标架构: ${arch}（DOCKER_DEFAULT_PLATFORM=${DOCKER_DEFAULT_PLATFORM}）"
}

sed_inplace() {
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "$@"
  else
    sed -i '' "$@"
  fi
}

set_kv() {
  local file="$1" key="$2" val="$3"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    sed_inplace "s|^${key}=.*|${key}=${val}|" "$file"
  else
    echo "${key}=${val}" >>"$file"
  fi
}

detect_host_ip() {
  local ip="${DEPLOY_HOST:-}"
  [[ -n "$ip" ]] && { echo "$ip"; return; }
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')" || true
  [[ -z "$ip" ]] && ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="src") print $(i+1)}')" || true
  [[ -z "$ip" ]] && ip="127.0.0.1"
  echo "$ip"
}

# 生成本机 platform/.env.docker（不修改 .env）
sync_deploy_env() {
  local arch="${1:-amd64}"
  local host tmp
  host="$(detect_host_ip)"
  local src_env="$PLATFORM/.env" out_env="$PLATFORM/.env.docker"
  local src_kf="$PLATFORM/knowflow.env" out_kf="$PLATFORM/knowflow.env.docker"
  local fallback_env="$PLATFORM/.env.example"
  local fallback_kf="$PLATFORM/knowflow.env.example"

  tmp="$(mktemp)"
  if [[ -f "$src_env" ]]; then
    cp "$src_env" "$tmp"
    info "sync env ← platform/.env"
  elif [[ -f "$out_env" ]]; then
    cp "$out_env" "$tmp"
  elif [[ -f "$fallback_env" ]]; then
    cp "$fallback_env" "$tmp"
    info "sync env ← .env.example"
  else
    cp "$PLATFORM/.env.example" "$tmp"
  fi

  sed_inplace \
    -e 's|@127\.0\.0\.1:5432|@postgres:5432|g' \
    -e 's|redis://127\.0\.0\.1:|redis://redis:|g' \
    -e 's|^MINIO_ENDPOINT=127\.0\.0\.1:9000|MINIO_ENDPOINT=minio:9000|' \
    -e 's|^MINIO_ENDPOINT=localhost:9000|MINIO_ENDPOINT=minio:9000|' \
    -e 's|^PDF2ZH_API_URL=http://127\.0\.0\.1:7861|PDF2ZH_API_URL=http://pdf2zh-api:7861|' \
    -e 's|^PDF2ZH_API_URL=http://localhost:7861|PDF2ZH_API_URL=http://pdf2zh-api:7861|' \
    -e 's|^SPEECH_SERVICE_URL=http://127\.0\.0\.1:8765|SPEECH_SERVICE_URL=http://speech-api:8765|' \
    -e 's|^SPEECH_SERVICE_URL=http://localhost:8765|SPEECH_SERVICE_URL=http://speech-api:8765|' \
    -e 's|^KNOWFLOW_BACKEND_URL=http://127\.0\.0\.1:5001|KNOWFLOW_BACKEND_URL=http://knowflow-backend:5000|' \
    -e 's|^KNOWFLOW_BACKEND_URL=http://localhost:5001|KNOWFLOW_BACKEND_URL=http://knowflow-backend:5000|' \
    -e 's|^RAGFLOW_API_URL=http://127\.0\.0\.1:9380|RAGFLOW_API_URL=http://ragflow-server:9380|' \
    -e 's|^RAGFLOW_API_URL=http://localhost:9380|RAGFLOW_API_URL=http://ragflow-server:9380|' \
    "$tmp"
  sed_inplace 's|^DEEPSEEK_API_KEY="\([^"]*\)"|DEEPSEEK_API_KEY=\1|' "$tmp"
  if grep -q '^SPEECH_MODELS_DIR=' "$tmp"; then
    sed_inplace 's|^SPEECH_MODELS_DIR=.*|SPEECH_MODELS_DIR=|' "$tmp"
  fi
  set_kv "$tmp" KNOWFLOW_ENABLED true
  set_kv "$tmp" DEPLOY_HOST "$host"
  set_kv "$tmp" FRONTEND_PORT "${FRONTEND_PORT:-40005}"
  set_kv "$tmp" DEPLOY_ARCH "$arch"
  mv "$tmp" "$out_env"

  tmp="$(mktemp)"
  if [[ -f "$src_kf" ]]; then
    cp "$src_kf" "$tmp"
  elif [[ -f "$out_kf" ]]; then
    cp "$out_kf" "$tmp"
  elif [[ "$arch" == amd64 && -f "$fallback_kf" ]]; then
    cp "$fallback_kf" "$tmp"
  else
    cp "$PLATFORM/knowflow.env.example" "$tmp"
  fi
  set_kv "$tmp" MACOS 0
  set_kv "$tmp" KNOWFLOW_DOCKER_NETWORK zhitanai_default
  if [[ "$arch" == amd64 ]]; then
    set_kv "$tmp" RAGFLOW_IMAGE zxwei/knowflow:v2.1.8
    set_kv "$tmp" KNOWFLOW_SERVER_IMAGE zxwei/knowflow-server:v2.1.8
    sed_inplace '/^KNOWFLOW_PLATFORM=/d' "$tmp"
    info "sync knowflow ← amd64 预构建镜像"
  else
    set_kv "$tmp" KNOWFLOW_PLATFORM linux/arm64
    set_kv "$tmp" RAGFLOW_PLATFORM linux/arm64
    sed_inplace '/^RAGFLOW_IMAGE=zxwei/d' "$tmp"
    info "sync knowflow ← arm64 源码构建配置"
  fi
  mv "$tmp" "$out_kf"
  info "已写入 .env.docker / knowflow.env.docker（arch=${arch}）"
}

sync_env_on_server() {
  cd "$PLATFORM"
  if [[ -f .env.docker ]]; then
    cp -f .env.docker .env
  else
    local arch
    arch="$(normalize_arch "${DEPLOY_ARCH:-auto}")"
    configure_for_arch "$arch"
    sync_deploy_env "$arch"
    cp -f .env.docker .env
  fi
  [[ -f knowflow.env.docker ]] && cp -f knowflow.env.docker knowflow.env
}

require_docker() {
  command -v docker >/dev/null 2>&1 || { error "未找到 docker"; exit 1; }
}

wait_pdf2zh_optional() {
  [[ "$DEPLOY_WAIT_PDF2ZH" == 1 ]] || return 0
  info "等待 pdf2zh-api 健康检查..."
  local i
  for i in $(seq 1 90); do
    curl -sf "http://127.0.0.1:7861/api/health" >/dev/null 2>&1 && return 0
    sleep 5
  done
  warn "pdf2zh-api 可能仍在 warmup"
}

warn_deepseek_key() {
  if [[ -f "$PLATFORM/.env" ]] && ! grep -qE '^DEEPSEEK_API_KEY=.+.' "$PLATFORM/.env" 2>/dev/null; then
    warn "未配置 DEEPSEEK_API_KEY，录音「总结」不可用"
  fi
}

_job_knowflow() {
  cd "$PLATFORM"
  bash "$ROOT/scripts/dev.sh" knowflow setup
  [[ -f knowflow.env ]] || cp -f knowflow.env.docker knowflow.env 2>/dev/null \
    || cp -f knowflow.env.example knowflow.env
  set -a
  # shellcheck disable=SC1091
  source knowflow.env
  set +a
  export COMPOSE_PROFILES="${COMPOSE_PROFILES:-infinity}"
  local -a kf_profile_args=() kf_compose=(-f "$KF_COMPOSE_FILE")
  local p
  IFS=',' read -ra _kf_prof <<< "${COMPOSE_PROFILES}"
  for p in "${_kf_prof[@]}"; do
    p="${p// /}"
    [[ -n "$p" ]] && kf_profile_args+=(--profile "$p")
  done
  if [[ "$DEPLOY_ARCH" == amd64 ]] && \
     { [[ "${DEPLOY_USE_MIRROR:-1}" == 1 ]] || [[ "${DEPLOY_USE_MIRROR:-auto}" == auto ]]; }; then
    kf_compose+=(-f docker-compose.knowflow.mirror.yml)
    info "[knowflow] amd64 + 镜像加速"
  fi
  if [[ "$DEPLOY_ARCH" == arm64 ]]; then
    warn "[knowflow] arm64 从源码构建，首次可能较久（勿改系统 Docker daemon 配置）"
    docker compose -p knowflow "${kf_profile_args[@]}" "${kf_compose[@]}" \
      --env-file knowflow.env build 2>/dev/null || true
  else
    docker compose -p knowflow "${kf_profile_args[@]}" "${kf_compose[@]}" \
      --env-file knowflow.env pull 2>/dev/null || true
  fi
  docker compose -p knowflow "${kf_profile_args[@]}" "${kf_compose[@]}" \
    --env-file knowflow.env up -d
}

_job_speech() {
  cd "$PLATFORM"
  local models="${SPEECH_MODELS_DIR:-$ROOT/.run/speech-models}"
  mkdir -p "$models"
  export SPEECH_MODELS_DIR="$models"
  info "[speech] 构建并启动 ..."
  $SPEECH_COMPOSE build --parallel
  $SPEECH_COMPOSE up -d
}

_job_core_build_up() {
  cd "$PLATFORM"
  info "[core] 并行构建 ..."
  $COMPOSE build --parallel
  $COMPOSE up -d
}

_job_core() {
  cd "$PLATFORM"
  $COMPOSE up -d postgres redis minio
  _job_core_build_up
}

_job_app() {
  cd "$PLATFORM"
  info "[app] 仅 api worker frontend pdf2zh-api ..."
  $COMPOSE build --parallel api worker frontend pdf2zh-api
  $COMPOSE up -d api worker frontend pdf2zh-api
}

start_app() {
  require_docker
  sync_env_on_server
  cd "$PLATFORM"
  _job_app
  wait_pdf2zh_optional
  warn_deepseek_key
}

start_core() {
  require_docker
  sync_env_on_server
  cd "$PLATFORM"
  $COMPOSE up -d postgres redis minio 2>/dev/null || true
  if [[ "$DEPLOY_PARALLEL" == 1 ]]; then
    _job_core
  else
    $COMPOSE up -d --build
  fi
  wait_pdf2zh_optional
}

start_full_parallel() {
  require_docker
  sync_env_on_server
  mkdir -p "$ROOT/.run"
  cd "$PLATFORM"
  $COMPOSE up -d postgres redis minio
  local pids=()
  (_job_knowflow) >"$ROOT/.run/deploy-knowflow.log" 2>&1 & pids+=($!)
  (_job_speech) >"$ROOT/.run/deploy-speech.log" 2>&1 & pids+=($!)
  (_job_core_build_up) >"$ROOT/.run/deploy-core.log" 2>&1 & pids+=($!)
  local p ec=0
  for p in "${pids[@]}"; do wait "$p" || ec=1; done
  $COMPOSE up -d api worker
  [[ "$ec" -ne 0 ]] && warn "部分并行任务失败，见 .run/deploy-*.log"
  wait_pdf2zh_optional
  warn_deepseek_key
}

read_frontend_port() {
  local port="${FRONTEND_PORT:-40005}" f
  for f in "$PLATFORM/.env.docker" "$PLATFORM/.env"; do
    if [[ -f "$f" ]]; then
      port="$(grep -E '^FRONTEND_PORT=' "$f" 2>/dev/null | cut -d= -f2- | tr -d '\r')" || true
      [[ -n "$port" ]] && break
    fi
  done
  echo "${port:-40005}"
}

print_urls() {
  local host port app_name
  host="$(detect_host_ip)"
  port="$(read_frontend_port)"
  app_name="$(read_platform_app_name "$ROOT")"
  cat <<EOF

${GREEN}=== ${app_name} 部署已提交 (${DEPLOY_ARCH}) ===${NC}
  平台 Web:     http://${host}:${port}/ai/
  平台 API:     http://${host}:8000/docs
  pdf2zh API:   http://${host}:7861
  RAGFlow:      http://${host}:9380

  日志: tail -f .run/deploy.log
  停止: bash scripts/deploy.sh local down

EOF
}

cmd_down() {
  cd "$PLATFORM"
  $COMPOSE down
  docker compose -p knowflow -f "$KF_COMPOSE_FILE" down 2>/dev/null || true
  $SPEECH_COMPOSE down 2>/dev/null || true
  info "已停止"
}

run_local_deploy() {
  local arch
  arch="$(normalize_arch "${DEPLOY_ARCH:-auto}")"
  configure_for_arch "$arch"
  case "$DEPLOY_MODE" in
    app)       start_app; print_urls ;;
    core|"")   start_core; print_urls ;;
    knowflow)  start_core; _job_knowflow; cd "$PLATFORM"; $COMPOSE up -d api worker; print_urls ;;
    speech)    start_core; _job_speech; warn_deepseek_key; print_urls ;;
    full)
      if [[ "$DEPLOY_PARALLEL" == 1 ]]; then start_full_parallel; else
        start_core; _job_knowflow; _job_speech
      fi
      print_urls
      ;;
    down|stop) cmd_down ;;
    *) error "未知模式: $DEPLOY_MODE"; exit 1 ;;
  esac
}

# --- 推送 ---
rsync_to_remote() {
  local dest="${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
  local -a opts=(-avz)
  [[ "$RSYNC_DELETE" == 1 ]] && opts+=(--delete)
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${DEPLOY_USER}@${DEPLOY_HOST}" "echo ok" >/dev/null
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}/.run'"
  info "rsync → ${dest}"
  rsync "${opts[@]}" \
    --exclude '.git/' --exclude '.venv/' --exclude '**/.venv/' \
    --exclude '**/node_modules/' --exclude '.run/' --exclude 'dist/' \
    --exclude '**/__pycache__/' --exclude '*.pyc' --exclude '.DS_Store' \
    --exclude 'platform/.env' --exclude 'platform/knowflow.env' \
    "$ROOT/" "$dest"
  rsync -avz "$PLATFORM/.env.docker" "${dest}platform/.env.docker"
  [[ -f "$PLATFORM/knowflow.env.docker" ]] && \
    rsync -avz "$PLATFORM/knowflow.env.docker" "${dest}platform/knowflow.env.docker"
}

remote_deploy_background() {
  local mirror="${DEPLOY_USE_MIRROR:-1}" parallel="${DEPLOY_PARALLEL:-1}" wait_flag=""
  [[ "${DEPLOY_WAIT_PDF2ZH:-0}" == 1 ]] && wait_flag="--wait"
  info "远程后台: deploy.sh local ${DEPLOY_MODE}（arch=${DEPLOY_ARCH}）"
  ssh -o BatchMode=yes "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
set -euo pipefail
cd '${DEPLOY_PATH}'
mkdir -p .run
export DEPLOY_ARCH='${DEPLOY_ARCH}'
export DEPLOY_USE_MIRROR='${mirror}'
export DEPLOY_PARALLEL='${parallel}'
if pgrep -f 'bash scripts/deploy.sh local ${DEPLOY_MODE}' >/dev/null 2>&1; then
  echo "已有部署进程，跳过"
  pgrep -af 'deploy.sh local' || true
  exit 0
fi
nohup env DEPLOY_ARCH='${DEPLOY_ARCH}' DEPLOY_USE_MIRROR='${mirror}' DEPLOY_PARALLEL='${parallel}' \
  bash scripts/deploy.sh local ${DEPLOY_MODE} ${wait_flag} \
  >> .run/deploy.log 2>&1 &
echo \$! > .run/deploy.pid
EOF
}

remote_status() {
  ssh -o BatchMode=yes "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
cd '${DEPLOY_PATH}'
echo "=== 架构 / 部署进程 ==="
grep -E '^DEPLOY_ARCH=' platform/.env.docker 2>/dev/null || true
pgrep -af 'deploy.sh local' || echo "(无)"
echo ""
echo "=== deploy.log (末 15 行) ==="
tail -15 .run/deploy.log 2>/dev/null || echo "(无)"
EOF
}

stack_image_tarball() {
  local arch ver
  arch="$(normalize_arch "${DEPLOY_ARCH:-auto}")"
  ver="${ZHITAN_VERSION:-$(read_repo_version "$ROOT")}"
  if [[ -f "$ROOT/.env" ]]; then
    # shellcheck disable=SC1091
    set -a && source "$ROOT/.env" && set +a
    ver="${ZHITAN_VERSION:-$ver}"
  fi
  echo "${ROOT}/images/zhitan-${ver}-${arch}.tar.gz"
}

rsync_stack_bundle() {
  local dest="${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
  local tarball
  tarball="$(stack_image_tarball)"
  [[ -f "$tarball" ]] || {
    error "未找到镜像包 ${tarball}，请先在本机: bash scripts/stack.sh build && bash scripts/stack.sh save"
    exit 1
  }
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}/images' '${DEPLOY_PATH}/data'"
  info "rsync 编排与镜像（不含业务源码）→ ${dest}"
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}/scripts' '${DEPLOY_PATH}/deploy/knowflow'"
  rsync -avz \
    "$ROOT/compose.yaml" \
    "$ROOT/compose.dev.yaml" \
    "$ROOT/.env.stack.example" \
    "$ROOT/deploy/" \
    "$tarball" \
    "${dest}"
  rsync -avz \
    "$ROOT/scripts/stack.sh" \
    "$ROOT/scripts/setup-stack-env.sh" \
    "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/scripts/"
  if [[ -f "$ROOT/.env" ]]; then
    rsync -avz "$ROOT/.env" "${dest}.env"
  elif [[ -f "$PLATFORM/.env.docker" ]]; then
    rsync -avz "$PLATFORM/.env.docker" "${dest}.env"
  fi
}

remote_stack_up() {
  local profiles="${STACK_PROFILES:-knowflow speech}"
  local tarball_name up_cmd="bash scripts/stack.sh up"
  local p
  for p in $profiles; do
    up_cmd+=" --profile ${p}"
  done
  tarball_name="$(basename "$(stack_image_tarball)")"
  ssh -o BatchMode=yes "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
set -euo pipefail
cd '${DEPLOY_PATH}'
bash scripts/stack.sh load "images/${tarball_name}"
${up_cmd}
EOF
}

run_stack_local() {
  load_env_root() {
    [[ -f "$ROOT/.env" ]] && return 0
    [[ -f "$PLATFORM/.env.docker" ]] && cp -f "$PLATFORM/.env.docker" "$ROOT/.env" && return 0
    warn "建议 cp .env.stack.example .env"
  }
  load_env_root
  local tarball profiles="${STACK_PROFILES:-knowflow speech}"
  tarball="$(stack_image_tarball)"
  if [[ -f "$tarball" ]]; then
    bash "$ROOT/scripts/stack.sh" load "$tarball"
  else
    warn "未找到 ${tarball}，将尝试使用本地已有镜像直接 up"
  fi
  local -a pargs=()
  local p
  for p in $profiles; do
    pargs+=(--profile "$p")
  done
  bash "$ROOT/scripts/stack.sh" up "${pargs[@]}"
}

run_stack_push() {
  load_target || { error "缺少 platform/deploy.target"; exit 1; }
  DEPLOY_ARCH="$(detect_remote_arch)"
  info "stack 部署 arch=${DEPLOY_ARCH}（仅镜像+编排，不 rsync 源码）"
  rsync_stack_bundle
  remote_stack_up
  info "远程 stack up 已执行。Web: http://${DEPLOY_HOST}:$(grep -E '^FRONTEND_PORT=' "$ROOT/.env" 2>/dev/null | cut -d= -f2 || echo 40005)/ai/"
}

run_push() {
  load_target || { error "缺少 platform/deploy.target（可从 deploy.target.example 复制）"; exit 1; }
  if [[ "$DO_STATUS" == 1 ]]; then
    remote_status
    exit 0
  fi
  DEPLOY_ARCH="$(detect_remote_arch)"
  configure_for_arch "$DEPLOY_ARCH"
  info "推送目标: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"
  if [[ "$DO_PUSH" == 1 ]]; then
    sync_deploy_env "$DEPLOY_ARCH"
    rsync_to_remote
  fi
  if [[ "$DO_DEPLOY" == 1 ]]; then
    if [[ "$DEPLOY_MODE" == down ]]; then
      ssh "${DEPLOY_USER}@${DEPLOY_HOST}" \
        "cd '${DEPLOY_PATH}' && DEPLOY_ARCH='${DEPLOY_ARCH}' bash scripts/deploy.sh local down"
    else
      remote_deploy_background
      info "本机已返回。查看: bash scripts/deploy.sh --status"
    fi
  else
    info "仅同步完成，部署: bash scripts/deploy.sh --deploy-only"
  fi
}

parse_args() {
  local -a positional=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      local)     RUN_LOCAL=1; shift ;;
      --push-only)   DO_DEPLOY=0; shift ;;
      --deploy-only) DO_PUSH=0; shift ;;
      --status)      DO_STATUS=1; DO_PUSH=0; DO_DEPLOY=0; shift ;;
      --wait)        DEPLOY_WAIT_PDF2ZH=1; shift ;;
      --serial)      DEPLOY_PARALLEL=0; shift ;;
      -h|--help)
        sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
      stack)
        DEPLOY_MODE="stack"; shift ;;
      app|core|knowflow|speech|full|down)
        DEPLOY_MODE="$1"; shift ;;
      *)
        positional+=("$1"); shift ;;
    esac
  done
  if [[ ${#positional[@]} -gt 0 ]]; then
    DEPLOY_MODE="${positional[0]}"
  fi
}

main() {
  if [[ "${1:-}" == "_sync-env" ]]; then
    shift || true
    local arch
    arch="$(normalize_arch "${DEPLOY_ARCH:-auto}")"
    sync_deploy_env "$arch"
    exit 0
  fi
  parse_args "$@"
  if [[ "$DEPLOY_MODE" != stack ]]; then
    error "DEPLOY_MODE=${DEPLOY_MODE} deprecated; use: deploy.sh stack push"
    error "See docs/zh/operations/deployment.md"
    exit 1
  fi
  if [[ "$RUN_LOCAL" == 1 ]]; then
    run_stack_local
  else
    run_stack_push
  fi
}

main "$@"
