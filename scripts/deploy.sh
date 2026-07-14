#!/usr/bin/env bash
# 企业 AI 知识库平台 — 生产部署：镜像 save/load 推送到远程（不 rsync 源码）
#
# 配置: backend/deploy.target（由 deploy.target.example 复制）
#
# 用法:
#   bash scripts/stack.sh build --profile knowflow --profile speech
#   bash scripts/stack.sh save
#   bash scripts/deploy.sh stack push      # 推送到 deploy.target 中的服务器
#   bash scripts/deploy.sh local stack     # 目标机本地 load + up
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/backend"
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

DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST=""
DEPLOY_PATH=""
DEPLOY_ARCH="${DEPLOY_ARCH:-auto}"
DEPLOY_TARGET="${DEPLOY_TARGET:-}"
TARGET_FILE=""

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

# --- 栈部署 ---
stack_image_tarball() {
  local arch ver
  arch="$(normalize_arch "${DEPLOY_ARCH:-auto}")"
  ver="${BENXI_VERSION:-$(read_repo_version "$ROOT")}"
  if [[ -f "$ROOT/.env" ]]; then
    # shellcheck disable=SC1091
    set -a && source "$ROOT/.env" && set +a
    ver="${BENXI_VERSION:-$ver}"
  fi
  echo "${ROOT}/images/benxi-${ver}-${arch}.tar.gz"
}

rsync_stack_bundle() {
  local dest="${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
  local use_registry="${DEPLOY_USE_REGISTRY:-0}"
  if [[ "$use_registry" == 1 ]]; then
    info "registry 模式：同步编排 + platform 源码（镜像从 ACR pull）→ ${dest}"
    ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}/scripts' '${DEPLOY_PATH}/third_party/deploy/knowflow' '${DEPLOY_PATH}/platform' '${DEPLOY_PATH}/configs/compose' '${DEPLOY_PATH}/configs/envs'"
    rsync -avz \
      "$ROOT/configs/compose/compose.yaml" "${dest}configs/compose/compose.yaml" \
      "$ROOT/configs/compose/compose.server.yaml" "${dest}configs/compose/compose.server.yaml" \
      "$ROOT/configs/compose/compose.mirror.yaml" "${dest}configs/compose/compose.mirror.yaml" \
      "$ROOT/configs/envs/.env.stack.example" "${dest}configs/envs/.env.stack.example" \
      "$ROOT/third_party/deploy/" \
      "$ROOT/backend/app/" \
      "${dest}backend/app/"
    rsync -avz \
      "$ROOT/backend/workers/" \
      "${dest}backend/workers/"
    rsync -avz \
      "$ROOT/scripts/stack.sh" \
      "$ROOT/scripts/setup-stack-env.sh" \
      "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/scripts/"
    if [[ -f "$ROOT/.env" ]]; then
      rsync -avz "$ROOT/.env" "${dest}.env"
    elif [[ -f "$PLATFORM/.env.docker" ]]; then
      rsync -avz "$PLATFORM/.env.docker" "${dest}.env"
    fi
    return
  fi
  local tarball
  tarball="$(stack_image_tarball)"
  [[ -f "$tarball" ]] || {
    error "未找到镜像包 ${tarball}，请先: bash scripts/stack.sh build && bash scripts/stack.sh save"
    error "或设置 DEPLOY_USE_REGISTRY=1 使用 ACR 镜像"
    exit 1
  }
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}/images' '${DEPLOY_PATH}/third_party/data'"
  info "tar 模式：同步编排与镜像包 → ${dest}"
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}/scripts' '${DEPLOY_PATH}/third_party/deploy/knowflow' '${DEPLOY_PATH}/configs/compose' '${DEPLOY_PATH}/configs/envs'"
  rsync -avz \
    "$ROOT/configs/compose/compose.yaml" "${dest}configs/compose/compose.yaml" \
    "$ROOT/configs/compose/compose.server.yaml" "${dest}configs/compose/compose.server.yaml" \
    "$ROOT/configs/compose/compose.dev.yaml" "${dest}configs/compose/compose.dev.yaml" \
    "$ROOT/configs/envs/.env.stack.example" "${dest}configs/envs/.env.stack.example" \
    "$ROOT/third_party/deploy/" \
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
  local use_registry="${DEPLOY_USE_REGISTRY:-0}"
  if [[ "$use_registry" == 1 ]]; then
    local profile_args=""
    local p
    for p in $profiles; do
      profile_args+=" --profile ${p}"
    done
    ssh -o BatchMode=yes "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
set -euo pipefail
cd '${DEPLOY_PATH}'
bash scripts/stack.sh pull-registry
bash scripts/stack.sh server-up${profile_args}
export INSTALL_BROWSER=1 SERVER_MOUNT_CODE=1
bash scripts/stack.sh build-browser || true
EOF
    return
  fi
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
    warn "建议 cp configs/envs/.env.stack.example .env"
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
  load_target || { error "缺少 backend/deploy.target"; exit 1; }
  DEPLOY_ARCH="$(detect_remote_arch)"
  info "stack 部署 arch=${DEPLOY_ARCH}（仅镜像+编排，不 rsync 源码）"
  rsync_stack_bundle
  remote_stack_up
  info "远程 stack up 已执行。Web: http://${DEPLOY_HOST}:$(grep -E '^FRONTEND_PORT=' "$ROOT/.env" 2>/dev/null | cut -d= -f2 || echo 40005)/ai/"
}

# --- 参数解析与入口 ---
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      local)     RUN_LOCAL=1; shift ;;
      -h|--help)
        sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
      stack)     shift ;;
      *)
        error "未知参数: $1（仅支持: deploy.sh [local] stack push）"
        exit 1
        ;;
    esac
  done
}

main() {
  parse_args "$@"
  if [[ "$RUN_LOCAL" == 1 ]]; then
    run_stack_local
  else
    run_stack_push
  fi
}

main "$@"
