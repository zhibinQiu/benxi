#!/usr/bin/env bash
# 安装浏览器 RPA（Playwright + Chromium）
# 本机 venv:  ./dev.sh browser setup
# 本机 Docker: ./dev.sh browser setup --docker
# 远程服务器: ./dev.sh browser setup --server
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
LOCAL_DEV_CONDA_ENV="${LOCAL_DEV_CONDA_ENV:-pdf2zh}"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'
info() { echo -e "${GREEN}[browser]${NC} $*"; }
step() { echo -e "→ $*"; }
error() { echo -e "${RED}[browser]${NC} $*" >&2; }

DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST="${DEPLOY_HOST:-}"
DEPLOY_PATH="${DEPLOY_PATH:-}"

load_deploy_target() {
  local f="$PLATFORM/deploy.target"
  [[ -f "$f" ]] || return 1
  # shellcheck disable=SC1090
  set -a && source "$f" && set +a
  DEPLOY_USER="${DEPLOY_USER:-root}"
  [[ -n "${DEPLOY_HOST:-}" && -n "${DEPLOY_PATH:-}" ]]
}

resolve_python() {
  if [[ -n "${LOCAL_DEV_PYTHON:-}" && -x "${LOCAL_DEV_PYTHON}" ]]; then
    echo "${LOCAL_DEV_PYTHON}"
    return 0
  fi
  if command -v conda >/dev/null 2>&1; then
    local base env_py
    base="$(conda info --base 2>/dev/null || true)"
    env_py="${base}/envs/${LOCAL_DEV_CONDA_ENV}/bin/python"
    if [[ -x "$env_py" ]]; then
      echo "$env_py"
      return 0
    fi
  fi
  if [[ -x "$PLATFORM/.venv/bin/python" ]]; then
    echo "$PLATFORM/.venv/bin/python"
    return 0
  fi
  command -v python3
}

browser_import_ok() {
  local py="$1"
  "$py" -c "from playwright.sync_api import sync_playwright" 2>/dev/null
}

setup_local() {
  local py
  py="$(resolve_python)"
  info "本机 Python: $py"
  cd "$PLATFORM"
  step "安装 Playwright Python 包（pip install -e '.[browser]'）…"
  "$py" -m pip install -e ".[browser]"
  step "下载 Chromium（playwright install chromium）…"
  "$py" -m playwright install chromium
  if browser_import_ok "$py"; then
    info "浏览器 RPA 本机依赖已就绪"
  else
    error "Playwright 安装后仍无法 import，请检查 pip 环境"
    exit 1
  fi
}

setup_docker() {
  command -v docker >/dev/null 2>&1 || { error "未找到 docker"; exit 1; }
  cd "$ROOT"
  COMPOSE_DEV=1 INSTALL_BROWSER=1 bash scripts/stack.sh build-browser
}

  rsync_build_files_to_server() {
  local dest="${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
  info "同步构建文件 → ${dest}"
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${DEPLOY_USER}@${DEPLOY_HOST}" \
    "mkdir -p '${DEPLOY_PATH}/platform/third_party/pageindex-upstream' '${DEPLOY_PATH}/scripts/lib'"
  rsync -avz "$ROOT/scripts/stack.sh" "${dest}scripts/stack.sh"
  rsync -avz "$ROOT/scripts/setup-browser-rpa.sh" "${dest}scripts/setup-browser-rpa.sh"
  rsync -avz "$ROOT/scripts/lib/browser-rpa.sh" "${dest}scripts/lib/browser-rpa.sh"
  rsync -avz \
    "$ROOT/compose.yaml" \
    "$ROOT/compose.server.yaml" \
    "${dest}"
  rsync -avz \
    "$ROOT/platform/Dockerfile" \
    "$ROOT/platform/pyproject.toml" \
    "$ROOT/platform/README.md" \
    "${dest}platform/"
  rsync -avz \
    "$ROOT/platform/third_party/pageindex-upstream/" \
    "${dest}platform/third_party/pageindex-upstream/" 2>/dev/null || true
}

setup_server() {
  load_deploy_target || {
    error "未找到 platform/deploy.target，无法 SSH 到服务器"
    exit 1
  }
  info "目标服务器: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${DEPLOY_USER}@${DEPLOY_HOST}" "echo ok" >/dev/null \
    || { error "SSH 连接失败"; exit 1; }

  rsync_build_files_to_server

  info "在服务器上构建 Playwright runtime（约 3–8 分钟）…"
  ssh -o BatchMode=yes "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
set -euo pipefail
cd '${DEPLOY_PATH}'
export INSTALL_BROWSER=1
export SERVER_MOUNT_CODE=1
export COMPOSE_PROJECT_NAME="\${COMPOSE_PROJECT_NAME:-lvye}"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
bash scripts/stack.sh build-browser
EOF
  info "服务器浏览器 RPA 已安装。Web: http://${DEPLOY_HOST}:40005/ai/"
}

MODE="${1:-local}"
case "$MODE" in
  local) setup_local ;;
  --docker|docker) setup_docker ;;
  --server|server) setup_server ;;
  *)
    error "用法: bash scripts/setup-browser-rpa.sh [local|--docker|--server]"
    exit 1
    ;;
esac
