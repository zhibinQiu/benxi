#!/usr/bin/env bash
# 清理 KnowFlow MySQL 中 progress=-1 的失败解析 task（终态记录，不影响队列消费）
#
#   bash scripts/knowflow-clear-failed-tasks.sh              # 远程（deploy.target）
#   bash scripts/knowflow-clear-failed-tasks.sh --local       # 本机 Docker 栈
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'
NC='\033[0m'
info() { echo -e "${GREEN}[knowflow-clear-failed]${NC} $*"; }

LOCAL=0
for arg in "$@"; do
  case "$arg" in
    --local) LOCAL=1 ;;
  esac
done

MYSQL_PASSWORD="${MYSQL_PASSWORD:-infini_rag_flow}"
MYSQL_DB="${MYSQL_DB:-rag_flow}"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-lvye}"
WORK_DIR="${WORK_DIR:-$ROOT}"

if [[ "$LOCAL" != 1 ]]; then
  DEPLOY_USER="${DEPLOY_USER:-root}"
  DEPLOY_HOST="${DEPLOY_HOST:-172.19.134.45}"
  WORK_DIR="${DEPLOY_PATH:-/root/qzb/lvye}"
  if [[ -f "$ROOT/platform/deploy.target" ]]; then
    # shellcheck disable=SC1091
    source "$ROOT/platform/deploy.target"
    WORK_DIR="${DEPLOY_PATH:-$WORK_DIR}"
  fi
  info "远程执行 → ${DEPLOY_USER}@${DEPLOY_HOST}:${WORK_DIR}"
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s -- \
    "${WORK_DIR}" "${COMPOSE_PROJECT}" "${MYSQL_PASSWORD}" "${MYSQL_DB}" <<'REMOTE'
set -euo pipefail
work_dir="$1"
compose_project="$2"
mysql_password="$3"
mysql_db="$4"
cd "${work_dir}"
compose=(docker compose -p "${compose_project}" -f compose.yaml -f deploy/knowflow.yml)
before="$("${compose[@]}" exec -T knowflow-mysql mysql -uroot -p"${mysql_password}" "${mysql_db}" -N \
  -e "SELECT COUNT(*) FROM task WHERE progress = -1" 2>/dev/null | tr -d '[:space:]')"
echo "[knowflow-clear-failed] 失败 task 清理前: ${before:-0}"
if [[ "${before:-0}" == "0" ]]; then
  echo "[knowflow-clear-failed] 无需清理"
  exit 0
fi
"${compose[@]}" exec -T knowflow-mysql mysql -uroot -p"${mysql_password}" "${mysql_db}" \
  -e "DELETE FROM task WHERE progress = -1;" >/dev/null 2>&1
after="$("${compose[@]}" exec -T knowflow-mysql mysql -uroot -p"${mysql_password}" "${mysql_db}" -N \
  -e "SELECT COUNT(*) FROM task WHERE progress = -1" 2>/dev/null | tr -d '[:space:]')"
echo "[knowflow-clear-failed] 失败 task 清理后: ${after:-0}（已删除 $((before - after)) 条）"
REMOTE
  exit 0
fi

cd "${WORK_DIR}"
compose=(docker compose -p "${COMPOSE_PROJECT}" -f compose.yaml -f deploy/knowflow.yml)
before="$("${compose[@]}" exec -T knowflow-mysql mysql -uroot -p"${MYSQL_PASSWORD}" "${MYSQL_DB}" -N \
  -e "SELECT COUNT(*) FROM task WHERE progress = -1" 2>/dev/null | tr -d '[:space:]')"
info "失败 task 清理前: ${before:-0}"
if [[ "${before:-0}" == "0" ]]; then
  info "无需清理"
  exit 0
fi
"${compose[@]}" exec -T knowflow-mysql mysql -uroot -p"${MYSQL_PASSWORD}" "${MYSQL_DB}" \
  -e "DELETE FROM task WHERE progress = -1;" >/dev/null 2>&1
after="$("${compose[@]}" exec -T knowflow-mysql mysql -uroot -p"${MYSQL_PASSWORD}" "${MYSQL_DB}" -N \
  -e "SELECT COUNT(*) FROM task WHERE progress = -1" 2>/dev/null | tr -d '[:space:]')"
info "失败 task 清理后: ${after:-0}（已删除 $((before - after)) 条）"
