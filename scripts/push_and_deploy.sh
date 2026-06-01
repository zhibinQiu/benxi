#!/usr/bin/env bash
# SSH 免密：rsync 同步 + 远程 nohup 并行部署（立即返回，不阻塞本机）
#
# 目标: platform/deploy.target
#
# 用法:
#   bash scripts/push_and_deploy.sh              # 同步 + 后台 full 并行部署
#   bash scripts/push_and_deploy.sh --deploy-only
#   bash scripts/push_and_deploy.sh --status     # 查看远程部署状态
#   bash scripts/push_and_deploy.sh --push-only
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
TARGET_FILE="${DEPLOY_TARGET:-$PLATFORM/deploy.target.amd64}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[push]${NC} $*"; }
warn()  { echo -e "${YELLOW}[push]${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST=""
DEPLOY_PATH=""
DEPLOY_MODE="full"
DO_PUSH=1
DO_DEPLOY=1
DO_STATUS=0
RSYNC_DELETE="${DEPLOY_RSYNC_DELETE:-0}"

load_target() {
  [[ -f "$TARGET_FILE" ]] || { error "缺少 $TARGET_FILE"; exit 1; }
  # shellcheck disable=SC1090
  set -a && source "$TARGET_FILE" && set +a
  DEPLOY_USER="${DEPLOY_USER:-root}"
  [[ -n "${DEPLOY_HOST:-}" && -n "${DEPLOY_PATH:-}" ]] \
    || { error "deploy.target.amd64 需设置 DEPLOY_HOST 与 DEPLOY_PATH"; exit 1; }
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --push-only)   DO_DEPLOY=0; shift ;;
      --deploy-only) DO_PUSH=0; shift ;;
      --status)      DO_STATUS=1; DO_PUSH=0; DO_DEPLOY=0; shift ;;
      -h|--help)
        sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
      core|knowflow|speech|full|down)
        DEPLOY_MODE="$1"; shift
        ;;
      *)
        DEPLOY_MODE="$1"; shift
        ;;
    esac
  done
}

prepare_env() {
  info "生成 amd64 部署配置（仅 .env.docker，不覆盖本地 .env）..."
  DEPLOY_TARGET="$TARGET_FILE" bash "$ROOT/scripts/sync_deploy_env.sh"
}

rsync_to_remote() {
  local dest="${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
  local -a rsync_opts=(-avz)

  [[ "$RSYNC_DELETE" == 1 ]] && rsync_opts+=(--delete)

  info "SSH 检查 ${DEPLOY_USER}@${DEPLOY_HOST} ..."
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${DEPLOY_USER}@${DEPLOY_HOST}" "echo ok" >/dev/null
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}/.run'"

  info "rsync → ${dest}"
  rsync "${rsync_opts[@]}" \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude '**/.venv/' \
    --exclude '**/node_modules/' \
    --exclude '.run/' \
    --exclude 'dist/' \
    --exclude '**/__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'platform/.env' \
    --exclude 'platform/knowflow.env' \
    --exclude 'platform/.env.docker' \
    --exclude 'platform/knowflow.env.docker' \
    "$ROOT/" "$dest"

  # amd64 部署配置（勿同步本地 Mac 用的 .env）
  if [[ ! -f "$PLATFORM/.env.docker" ]]; then
    error "缺少 platform/.env.docker，请先运行 sync_deploy_env.sh"
    exit 1
  fi
  rsync -avz \
    "$PLATFORM/.env.docker" \
    "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/platform/.env.docker"
  if [[ -f "$PLATFORM/knowflow.env.docker" ]]; then
    rsync -avz \
      "$PLATFORM/knowflow.env.docker" \
      "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/platform/knowflow.env.docker"
  fi
}

remote_deploy_background() {
  local mirror="${DEPLOY_USE_MIRROR:-1}"
  local parallel="${DEPLOY_PARALLEL:-1}"
  local wait_flag=""
  [[ "${DEPLOY_WAIT_PDF2ZH:-0}" == 1 ]] && wait_flag="--wait"

  info "远程后台部署: deploy_amd64.sh ${DEPLOY_MODE}（并行=${parallel}）"

  ssh -o BatchMode=yes "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
set -euo pipefail
cd '${DEPLOY_PATH}'
mkdir -p .run
if pgrep -f 'bash scripts/deploy_amd64.sh ${DEPLOY_MODE}' >/dev/null 2>&1; then
  echo "已有部署进程在运行，跳过重复启动"
  pgrep -af 'deploy_amd64.sh' || true
  exit 0
fi
nohup env DEPLOY_USE_MIRROR=${mirror} DEPLOY_PARALLEL=${parallel} \
  bash scripts/deploy_amd64.sh ${DEPLOY_MODE} ${wait_flag} \
  >> .run/deploy.log 2>&1 &
echo \$! > .run/deploy.pid
echo "DEPLOY_PID=\$(cat .run/deploy.pid)"
EOF
}

remote_status() {
  ssh -o BatchMode=yes "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
cd '${DEPLOY_PATH}'
echo "=== 部署进程 ==="
pgrep -af 'deploy_amd64.sh' || echo "(无)"
echo ""
echo "=== 容器 ==="
cd platform 2>/dev/null && docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.mirror.yml ps -a 2>/dev/null | head -20 || true
echo ""
echo "=== deploy.log (末 15 行) ==="
tail -15 .run/deploy.log 2>/dev/null || echo "(无日志)"
echo ""
echo "=== deploy-core.log (末 8 行) ==="
tail -8 .run/deploy-core.log 2>/dev/null || true
EOF
}

main() {
  parse_args "$@"
  load_target

  if [[ "$DO_STATUS" == 1 ]]; then
    remote_status
    exit 0
  fi

  info "目标: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"

  if [[ "$DO_PUSH" == 1 ]]; then
    prepare_env
    rsync_to_remote
  fi

  if [[ "$DO_DEPLOY" == 1 ]]; then
    if [[ "$DEPLOY_MODE" == down ]]; then
      ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "cd '${DEPLOY_PATH}' && bash scripts/deploy_amd64.sh down"
      info "已发送停止命令"
    else
      remote_deploy_background
      info "本机已返回。查看进度:"
      info "  bash scripts/push_and_deploy.sh --status"
      info "  ssh ${DEPLOY_USER}@${DEPLOY_HOST} 'tail -f ${DEPLOY_PATH}/.run/deploy.log'"
      info "访问: http://${DEPLOY_HOST}"
    fi
  else
    info "仅同步完成（--push-only）"
    info "  bash scripts/push_and_deploy.sh --deploy-only"
  fi
}

main "$@"
